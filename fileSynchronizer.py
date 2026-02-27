#!/usr/bin/python3
#==============================================================================
#description     :This is a skeleton code for programming assignment 
#usage           :python Skeleton.py trackerIP trackerPort
#python_version  :>= 3.5
#Authors         :Yongyong Wei, Rong Zheng
#==============================================================================

import socket, sys, threading, json,time,os,ssl
import os.path
import glob
import json
import optparse

def validate_ip(s):
    """
    Validate the IP address of the correct format
    Arguments: 
    s -- dot decimal IP address in string
    Returns:
    True if valid; False otherwise
    """
    a = s.split('.')
    if len(a) != 4:
        return False
    for x in a:
        if not x.isdigit():
            return False
        i = int(x)
        if i < 0 or i > 255:
            return False
    return True

def validate_port(x):
    """Validate the port number is in range [0,2^16 -1 ]
    Arguments:
    x -- port number
    Returns:
    True if valid; False, otherwise
    """
    if not x.isdigit():
        return False
    i = int(x)
    if i < 0 or i > 65535:
            return False
    return True

def get_file_info():
    """Get file info in the local directory (subdirectories are ignored).
    Return: a JSON array of {'name':file,'mtime':mtime}
    i.e, [{'name':file,'mtime':mtime},{'name':file,'mtime':mtime},...]
    Hint: a. you can ignore subfolders, *.so, *.py, *.dll, and this script
          b. use os.path.getmtime to get mtime, and round down to integer
    """
    file_arr = []

    ignore = {'.py', '.so', '.dll'}
    current_script = os.path.basename(__file__)
    
    for entry in os.scandir('.'):
        if entry.isfile() and entry.name != current_script:
            if not any(entry.name.endswith(ext) for ext in ignore):
                mtime = int(os.path.getmtime(entry.path))
                file_arr.append({'name': entry.name, 'mtime': mtime})
    return file_arr

def get_files_dic():
    """Get file info as a dictionary {name: mtime} in local directory.
    Hint: same filtering rules as get_file_info().
    """
    file_dic = {}
    
    array = get_file_info()
    for item in array:
        file_dic[item['name']] = item['mtime']

    return file_dic

def check_port_avaliable(check_port):
    """Check if a port is available
    Arguments:
    check_port -- port number
    Returns:
    True if valid; False otherwise
    """
    if str(check_port) in os.popen("netstat -na").read():
        return False
    return True
	
def get_next_avaliable_port(initial_port):
    """Get the next available port by searching from initial_port to 2^16 - 1
       Hint: You can call the check_port_avaliable() function
             Return the port if found an available port
             Otherwise consider next port number
    Arguments:
    initial_port -- the first port to check

    Return:
    port found to be available; False if no port is available.
    """

    currPort = initial_port
    while currPort <= 65535:
        if check_port_avaliable(currPort):
            return currPort
        currPort += 1
    return False


class FileSynchronizer(threading.Thread):
    def __init__(self, trackerhost,trackerport,port, host='0.0.0.0'):

        threading.Thread.__init__(self)

        #Own port and IP address for serving file requests to other peers
        self.port = port
        self.host = host

        #Tracker IP/hostname and port
        self.trackerhost = trackerhost
        self.trackerport = trackerport

        self.BUFFER_SIZE = 8192

        #Create a TCP socket to communicate with the tracker
        self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.client.settimeout(180)
        self._tracker_buf = b''

    
        #Store the message to be sent to the tracker. 
        #Initialize to the Init message that contains port number and file info.
        #Refer to Table 1 in Instructions.pdf for the format of the Init message
        #You can use json.dumps to conver a python dictionary to a json string
	    #Encode using UTF-8
        self.msg = (json.dumps({"port": self.port, "files": get_file_info()}) + '\n').encode('utf-8')

        #Create a TCP socket to serve file requests from peers.
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        try:
            self.server.bind((self.host, self.port))
        except socket.error:
            print(('Bind failed %s' % (socket.error)))
            sys.exit()
        self.server.listen(10)

    def fatal_tracker(self, message, exc=None):
        """Abort the process on tracker failure"""
        if exc is not None:
            print((message, exc))
        else:
            print(message)
        try:
            self.server.close()
        except Exception:
            pass
        os._exit(1)


    # Not currently used. Ensure sockets are closed on disconnect
    def exit(self):
        self.server.close()

    #Handle file request from a peer(i.e., send the file content to peers)
    def process_message(self, conn, addr):
        '''
        Arguments:
        self -- self object
        conn -- socket object for an accepted connection from a peer
        addr -- IP address of the peer (only used for testing purpose)
        '''
        try:
            #Step 1. read the file name terminated by '\n'
            request_data = b''
            while b'\n' not in request_data:
                chunk = conn.recv(self.BUFFER_SIZE)
                if not chunk: break
                request_data += chunk

            filename= request_data.decode('utf-8').strip()
            #Step 2. read content of that file in binary mode
            if os.path.exists(filename):
                filesize = os.path.getsize(filename)
                header = f"Content-Length: {filesize}\n".encode('utf-8')
                conn.sendall(header)
                
                #Step 3. send header "Content-Length: <size>\n" then file bytes
                with open(filename, 'rb') as f:
                    while True:
                        bytes_read = f.read(self.BUFFER_SIZE)
                        if not bytes_read: break
                        conn.sendall(bytes_read)
        except Exception as e:
            print(f"Error processing message from {addr}: {e}")
        finally:
            #Step 4. close conn when you are done.
            conn.close()

    def run(self):
        #Step 1. connect to tracker; on failure, may terminate

        try:
            self.client.connect((self.trackerhost, self.trackerport))
        except socket.error as e:
            self.fatal_tracker("Failed to connect to tracker", e)

        t = threading.Timer(2, self.sync)
        t.start()
        print(('Waiting for connections on port %s' % (self.port)))
        while True:
            #Hint: guard accept() with try/except and exit cleanly on failure
            try: 
                conn, addr = self.server.accept()
                threading.Thread(target=self.process_message, args=(conn,addr)).start()
            except socket.error:
                break

    def sync(self):
        print(('connect to:'+self.trackerhost,self.trackerport))
        #Step 1. send Init msg to tracker (Note init msg only sent once)
        #Since self.msg is already initialized in __init__, you can send directly
        #Hint: on send failure, may terminate

        try:
            self.client.sendall(self.msg)
            #Step 2. now receive a directory response message from tracker
            while b'\n' not in self._tracker_buf:
                chunk = self.client.recv(self.BUFFER_SIZE)
                if not chunk:
                    raise socket.error("Tracker connection lost.")
                self._tracker_buf += chunk

            line, self._tracker_buf = self._tracker_buf.split(b'\n', 1)
            directory_response_message = line.decode('utf-8')
            print('received from tracker:', directory_response_message)

            directory = json.loads(directory_response_message)
            local_files = get_files_dic()

            for filename, info in directory_data.items():
                remote_mtime = info['mtime']
                remote_ip = info['ip']
                remote_port = info['port']

                is_self = (remote_port == self.port and remote_ip in ['127.0.0.1', '0.0.0.0', self.host])
                
                if not is_self:
                    if filename not in local_files or remote_mtime > local_files[filename]:
                        # Hint c: Call syncfile for new/updated files
                        # Note: syncfile handles hints d, e, and f internally.
                        self.syncfile(filename, info)


        #Step 4. construct a KeepAlive message
        #Note KeepAlive msg is sent multiple times, the format can be found in Table 1
                keepalive_data = {"port": self.port}
                self.msg = (json.dumps(keepalive_data) + '\n').encode('utf-8') #YOUR CODE
        except (socket.error, json.JSONDecodeError) as e:
            self.fatal_tracker("Synchronization cycle failed", e)

        #Step 5. start timer
        t = threading.Timer(5, self.sync)
        t.daemon = True
        t.start()

    def syncfile(self, filename, file_dic):
        """Fetch a file from a peer and store it locally.

        Arguments:
        filename -- file name to request
        file_dic -- dict with 'ip', 'port', and 'mtime'
        """
        #YOUR CODE
        #Step 1. connect to peer and send filename + '\n'
        #Step 2. read header "Content-Length: <size>\n"
        #Step 3. read exactly <size> bytes; if short, discard partial file
        #Step 4. write file to disk (binary), rename from .part when done
        #Step 5. set mtime using os.utime

if __name__ == '__main__':
    parser = optparse.OptionParser(usage="%prog ServerIP ServerPort")
    try:
        options, args = parser.parse_args()
    except SystemExit:
        sys.exit(1)

    if len(args) < 1:
        parser.error("No ServerIP and ServerPort")
    elif len(args) < 2:
        parser.error("No  ServerIP or ServerPort")
    else:
        if validate_ip(args[0]) and validate_port(args[1]):
            tracker_ip = args[0]
            tracker_port = int(args[1])

            # get a free port
            synchronizer_port = get_next_avaliable_port(8000)
            synchronizer_thread = FileSynchronizer(tracker_ip,tracker_port,synchronizer_port)
        else:
            parser.error("Invalid ServerIP or ServerPort")
