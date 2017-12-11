import socket
import json
import argparse
from threading import Thread
from multiprocessing import Queue
from time import sleep, time


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

    def post_pairs_request(self, pairs, first=None):
        data = {'code': 'POST_PAIRS', 'pairs': pairs, 'mode': Server.MODE}
        if first is not None:
            data['first'] = first
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

    def send_pairs(self, pairs, first=None):
        self.__pairs = pairs
        while not self.post_pairs_request(pairs, first):
            pass

    def send_begin(self):
        while not self.post_begin_request():
            pass
        print('{}:BEGIN'.format(self.__id))

    def get_port(self):
        return self.__port

    def get_status_info_request(self):
        data = {'code': 'GET_STATUS_INFO'}
        self.__socket.send(json.dumps(data).encode('utf-8'))
        response = json.loads(self.__socket.recv(1024).decode('utf-8'))
        if response is not None and 'code' in response and response[
            'code'] == 'GET_STATUS_INFO_RESPONSE' and set(response.keys()) == {'code', 'token', 'deadlocks', 'meals',
                                                                               'messagesSent', 'messagesReceived'}:
            return response
        return None

    def get_status_info(self):
        count = self.get_status_info_request()
        while count is None:
            count = self.get_status_info_request()
        return count

    def post_kill_signal(self):
        data = {'code': 'TIME_TO_DIE'}
        self.__socket.send(json.dumps(data).encode('utf-8'))
        response = json.loads(self.__socket.recv(1024).decode('utf-8'))
        if response is not None and 'code' in response and response[
            'code'] == 'FINALLY_DEAD_RESPONSE' and set(response.keys()) == {'code', 'token', 'deadlocks', 'meals',
                                                                               'messagesSent', 'messagesReceived'}:
            return response
        return None

    def send_kill_signal(self):
        info = self.post_kill_signal()
        while info is None:
            info = self.post_kill_signal()
        return info

    def run(self):
        while not self.get_port_request():
            pass
        print(self.__port)
        while True:
            if not self.__queue.empty():
                item = self.__queue.get()
                self.__socket.send(item.encode('utf-8'))


class Server(Thread):
    MODE = ''

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
        self.__start_time = None

        Thread.__init__(self)

    def killme(self):
        self.__killme = True

    def get_start_time(self):
        return self.__start_time

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
                for i, connection in enumerate(self.__connections):
                    first = None
                    if i == 0:
                        first = self.__pairs[connection.get_full_address()][-1]
                    print("{} - {}".format(connection.get_full_address(), self.__pairs[connection.get_full_address()]))
                    connection.send_pairs(self.__pairs[connection.get_full_address()], first)

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
                    self.__start_time = time()
                    print('Beginning dinner')
                    self.__stage = 'RUNNING'

            if self.__stage == 'RUNNING':
                for c in self.__connections:
                    info = c.get_status_info()
                    Server.print_status(c.get_full_address(), info['token'], info['deadlocks'], info['meals'],
                                        info['messagesSent'], info['messagesReceived'])
                sleep(0.5)

    @staticmethod
    def print_status(address, token, deadlocks, meals, messages_sent, messages_received):
        print('Philosopher {}'.format(address))
        print('    {}'.format(token))
        print('    {} deadlocks'.format(deadlocks))
        print('    {} meals'.format(meals))
        print('    {} messages sent'.format(messages_sent))
        print('    {} messages received'.format(messages_received))

    def send_kill_signal(self):
        for c in self.__connections:
            result = c.send_kill_signal()
            Server.print_status(c.get_full_address(), result['token'], result['deadlocks'], result['meals'],
                                result['messagesSent'], result['messagesReceived'])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", help="application port",
                        type=int)
    parser.add_argument('--philosophers', help="number of philosophers", type=int)
    parser.add_argument('--duration', help="Dinner's max duration", type=int)
    parser.add_argument('--token', help="Token mode", action='store_true')
    args = parser.parse_args()
    duration = args.duration

    Server.MODE = 'TOKEN' if args.token else 'WITHOUT_TOKEN'
    print(Server.MODE)

    start_time = time()

    queue = Queue()
    server = Server(queue, args.port, args.philosophers)
    server.start()

    while server.get_start_time() is None or ((time() - server.get_start_time()) < duration):
        pass

    print('Killing everybody\n\n')
    server.send_kill_signal()
    server.killme()
    server.join()






