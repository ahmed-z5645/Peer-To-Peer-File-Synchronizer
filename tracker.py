import socket, sys, threading, json,time,optparse,os

def validate_ip(s):
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
    if not x.isdigit():
        return False
    i = int(x)
    if i < 0 or i > 65535:
            return False
    return True

class Tracker(threading.Thread):
    def __init__(self, port, host='0.0.0.0'):
        threading.Thread.__init__(self)
        self.port = port
        self.host = host
        self.BUFFER_SIZE = 8192
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.users = {} # current connections  self.users[(ip,port)] = {'exptime':int(time.time())+self.user_timeout,'crt':'','key':''}
        self.files = {} #{'ip':addr[0],'port':data_dic['port'],'mtime':item['mtime']}
        self.user_timeout = 180
        self.lock = threading.Lock()
        try:
            self.server.bind((self.host, self.port))
        except socket.error:
            print(('Bind failed %s' % (socket.error)))
            sys.exit()
        self.server.listen(10)


    def check_user(self):
        cur_time = int(time.time())
        with self.lock:
            for k, v in list(self.users.items()):
                if (v['exptime']) < cur_time:
                    self.users.pop(k)
                    for filek, filev in list(self.files.items()):
                        print(('delete',k, filek))
                        if (filev['ip'] is k[0]) and (filev['port'] == k[1]):
                            self.files.pop(filek)
        t = threading.Timer(10, self.check_user)
        t.start()
        
    #Ensure sockets are closed on disconnect
    def exit(self):
        self.server.close()

    def run(self):
        print(('Waiting for connections on port %s' % (self.port)))
        t = threading.Timer(20, self.check_user)
        t.start()
        while True:
            try:
                conn, addr = self.server.accept()
            except socket.error as exc:
                print(('Accept failed:', exc))
                try:
                    self.server.close()
                except Exception:
                    pass
                return
            threading.Thread(target=self.process_messages, args=(conn, addr)).start()


    def process_messages(self, conn, addr):
        conn.settimeout(180.0)
        print(('Client connected with ' + addr[0] + ':' + str(addr[1])))

        buffer = b''
        while True:
            try:
                part = conn.recv(self.BUFFER_SIZE)
            except (socket.timeout, socket.error):
                conn.close()
                return
            if not part:
                break
            buffer += part
            while b'\n' in buffer:
                line, buffer = buffer.split(b'\n', 1)
                if not line:
                    continue
                try:
                    data_dic = json.loads(line.decode('utf-8'))
                except:
                    conn.close()
                    return
            
                # sync and send files json data
                if 'port' in data_dic:
                    print(('client server'+addr[0] + ':' + str(data_dic['port'])))
                    msg = ''
                    with self.lock:
                        if (addr[0], data_dic['port']) not in self.users:
                            self.users[(addr[0], data_dic['port'])] = {'exptime': (int(time.time()) + self.user_timeout),
                                                                   'crt': '','key':''}
                        else:
                            self.users[(addr[0], data_dic['port'])]['exptime'] = (int(time.time()) + self.user_timeout)
                        if 'crt' in data_dic and 'key' in data_dic :
                            self.users[(addr[0], data_dic['port'])]['crt'] = data_dic['crt']
                            self.users[(addr[0], data_dic['port'])]['key'] = data_dic['key']


                    # update files
                    if 'files' in data_dic:
                        with self.lock:
                            for item in data_dic['files']:
                                if item['name'] in self.files:
                                    if item['mtime'] > self.files[item['name']]['mtime']:
                                        self.files[item['name']] = {'ip':addr[0],'port':data_dic['port'],'mtime':item['mtime']}
                                else:
                                    self.files[item['name']] = {'ip':addr[0],'port':data_dic['port'],'mtime':item['mtime']}
                    with self.lock:
                        msg = json.dumps(self.files)
                    try:
                        conn.sendall((msg + '\n').encode('utf-8'))
                    except (socket.timeout, socket.error):
                        conn.close()
                        return

                # send crt,key of (serverip,serverport)
                if 'serverip' in data_dic and 'serverport' in data_dic:
                    msg = json.dumps({'crt':None,'key':None})
                    with self.lock:
                        if (data_dic['serverip'],data_dic['serverport']) in self.users:
                            msg = json.dumps({'crt':self.users[ (data_dic['serverip'],data_dic['serverport']) ]['crt'],
                                              'key':self.users[ (data_dic['serverip'],data_dic['serverport']) ]['key']})
                    try:
                        conn.sendall((msg + '\n').encode('utf-8'))
                    except (socket.timeout, socket.error):
                        conn.close()
                        return

        conn.close() # Close

if __name__ == '__main__':
    parser = optparse.OptionParser(usage="%prog ServerIP ServerPort")
    options, args = parser.parse_args()
    if len(args) < 1:
        parser.error("No ServerIP and ServerPort")
    elif len(args) < 2:
        parser.error("No  ServerIP or ServerPort")
    else:
        if validate_ip(args[0]) and validate_port(args[1]):
            server_ip = args[0]
            server_port = int(args[1])
        else:
            parser.error("Invalid ServerIP or ServerPort")
    tracker = Tracker(server_port,server_ip)
    tracker.start()
