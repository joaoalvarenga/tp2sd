import socket
import json
import argparse
from threading import Thread
from multiprocessing import Queue


class Connected(Thread):
    def __init__(self, id, socket, client):
        self.__socket = socket
        self.__client = client
        self.__queue = Queue()
        self.__port = None
        self.__id = id
        self.__ready_to_start = False
        self.__pairs = []

        Thread.__init__(self)

    def set_id(self, id):
        self.__id = id

    def get_id(self):
        return self.__id

    def get_queue(self):
        return self.__queue

    def get_full_address(self):
        return '{}:{}'.format(self.__client[0], self.__port)

    def is_ready(self):
        result = self.get_ready_request()
        while result is None:
            result = self.get_ready_request()
        return result

    def get_ready_request(self):
        data = {'code': 'GET_READY'}
        self.__socket.send(json.dumps(data).encode('utf-8'))
        response = json.loads(self.__socket.recv(1024).decode('utf-8'))
        if response is not None and 'code' in response and response[
            'code'] == 'GET_READY_RESPONSE' and 'ready' in response and response['ready'] is not None:
            return response['ready']

        return None

    def get_port_request(self):
        data = {'code': 'GET_PORT'}
        self.__socket.send(json.dumps(data).encode('utf-8'))
        response = json.loads(self.__socket.recv(1024).decode('utf-8'))
        if response is not None and 'code' in response and response[
            'code'] == 'GET_PORT_RESPONSE' and 'port' in response and response['port'] is not None:
            self.__port = response['port']
            return True

        return False

    def post_pairs_request(self, pairs):
        data = {'code': 'POST_PAIRS', 'pairs': pairs}
        self.__socket.send(json.dumps(data).encode('utf-8'))
        response = json.loads(self.__socket.recv(1024).decode('utf-8'))
        if response is not None and 'code' in response and response['code'] == 'POST_PAIR_RESPONSE':
            self.__ready_to_start = True
            return True
        return False

    def post_begin_request(self):
        data = {'code': 'POST_BEGIN'}
        self.__socket.send(json.dumps(data).encode('utf-8'))
        response = json.loads(self.__socket.recv(1024).decode('utf-8'))
        if response is not None and 'code' in response and response['code'] == 'BEGIN_RESPONSE':
            self.__ready_to_start = True
            return True
        return False

    def send_pairs(self, pairs):
        self.__pairs = pairs
        while not self.post_pairs_request(pairs):
            pass

    def send_begin(self):
        while not self.post_begin_request():
            pass
        print('{}:BEGIN'.format(self.__id))

    def get_port(self):
        return self.__port

    def run(self):
        while not self.get_port_request():
            pass
        print(self.__port)
        while True:
            if not self.__queue.empty():
                item = self.__queue.get()
                self.__socket.send(item.encode('utf-8'))


class Server(Thread):
    def __init__(self, queue, port, max_connections):
        self.__socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.__socket.bind(("0.0.0.0", port))
        self.__socket.listen(1)
        self.__queue = queue
        self.__killme = False
        self.__max_connections = max_connections

        self.__connections = []
        self.__pairs = {}

        print('Initializing on port {}'.format(port))
        print('Waiting for {} philosophers'.format(max_connections))
        self.__stage = 'INIT'

        Thread.__init__(self)

    def calculate_pairs(self):
        flag = True
        while flag:
            for c in self.__connections:
                flag = (c.get_port() is None)

        for i in range(len(self.__connections)):
            self.__connections[i].set_id(i)
            if i == 0:
                self.__pairs[self.__connections[i].get_full_address()] = [self.__connections[-1].get_full_address(),
                                   self.__connections[i + 1].get_full_address()]
            elif i == len(self.__connections) - 1:
                self.__pairs[self.__connections[i].get_full_address()] = [self.__connections[i - 1].get_full_address(),
                                   self.__connections[0].get_full_address()]
            else:
                self.__pairs[self.__connections[i].get_full_address()] = [self.__connections[i - 1].get_full_address(),
                                   self.__connections[i + 1].get_full_address()]

    def run(self):
        while not self.__killme:
            while len(self.__connections) < self.__max_connections:
                con, cliente = self.__socket.accept()
                self.__connections.append(Connected(len(self.__connections), con, cliente))
                self.__connections[-1].start()

            if len(self.__connections) == self.__max_connections and self.__stage == 'INIT':
                print('{} philosophers connected, distribuiting pairs.'.format(self.__max_connections))
                self.calculate_pairs()
                for connection in self.__connections:
                    print("{} - {}".format(connection.get_full_address(), self.__pairs[connection.get_full_address()]))
                    connection.send_pairs(self.__pairs[connection.get_full_address()])

                print('Waiting all philosophers get ready.')
                self.__stage = 'WAITING_READY'

            if self.__stage == 'WAITING_READY':
                flag = False
                for c in self.__connections:
                    flag = c.is_ready()
                if flag:
                    self.__stage = 'READY'
                    for c in self.__connections:
                        c.send_begin()
                    print('Beginning dinner')


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", help="display a square of a given number",
                        type=int)
    args = parser.parse_args()

    queue = Queue()
    server = Server(queue, args.port, 20)
    server.start()


