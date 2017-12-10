import argparse
import json
import socket
from functools import reduce
from threading import Thread
from multiprocessing import Queue
from random import randint
from time import sleep

class ManagerClient(Thread):
    def __init__(self, port):
        self.__socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.__killme = False
        self.__port = port
        self.__ready = False
        self.__pairs = None
        self.__begin = False

        Thread.__init__(self)

    def get_begin(self):
        return self.__begin

    def is_ready(self):
        return self.__ready

    def get_pairs(self):
        return self.__pairs

    def set_ready(self, ready):
        self.__ready = ready

    def run(self):
        self.__socket.connect(("127.0.0.1", 8980))
        while not self.__killme:
            request = json.loads(self.__socket.recv(1024).decode('utf-8'))
            if request is not None:
                if 'code' in request:
                    if request['code'] == 'GET_PORT':
                        self.__socket.send(json.dumps({'code': 'GET_PORT_RESPONSE',
                                                       'port': self.__port}).encode('utf-8'))
                    elif request['code'] == 'POST_PAIRS' and 'pairs' in request:
                        self.__pairs = request['pairs']
                        self.__socket.send(json.dumps({'code': 'POST_PAIR_RESPONSE'}).encode('utf-8'))
                    elif request['code'] == 'GET_READY':
                        self.__socket.send(json.dumps({'code': 'GET_READY_RESPONSE', 'ready': self.__ready}).encode('utf-8'))
                    elif request['code'] == 'POST_BEGIN':
                        self.__begin = True
                        self.__socket.send(json.dumps({'code': 'BEGIN_RESPONSE'}).encode('utf-8'))


class PhilosopherServerConnection(Thread):
    def __init__(self, id, socket, client):
        self.__id = id
        self.__socket = socket
        self.__address = client[0]
        self.__killme = False

        Thread.__init__(self)

    def get_address(self):
        return self.__address

    def run(self):
        while not self.__killme:
            request = json.loads(self.__socket.recv(1024).decode('utf-8'))
            if request is not None:
                if 'code' in request:
                    # print('req {}'.format(request))
                    if request['code'] == 'GET_FORK_STATUS' and 'port' in request and request['port'] is not None:
                        response = {'code': 'GET_FORK_STATUS_RESPONSE',
                                    'withFork': Philosopher.WITH_FORK['{}:{}'.format(self.__address, request['port'])],
                                    'state': Philosopher.STATE}
                        self.__socket.send(json.dumps(response).encode('utf-8'))


class PhilosopherServer(Thread):
    def __init__(self, port):
        self.__socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.__socket.bind(("0.0.0.0", port))
        self.__socket.listen(1)
        self.__queue = Queue()
        self.__killme = False
        self.__connections = []

        self.__ready = False

        Thread.__init__(self)

    def get_addresses(self):
        return [c.get_address() for c in self.__connections]

    def get_ready(self):
        return self.__ready

    def run(self):
        while not self.__killme:
            self.__ready = True
            con, cliente = self.__socket.accept()
            self.__connections.append(PhilosopherServerConnection(len(self.__connections), con, cliente))
            self.__connections[-1].start()


class PhilosopherClient(object):
    def __init__(self, address, port):
        self.__socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.__address = (address, port)
        print(self.__address)

        self.__socket.connect(self.__address)

    def get_address(self):
        return '{}:{}'.format(self.__address[0], self.__address[1])

    def __get_with_fork_request(self, port):
        request = {'code': 'GET_FORK_STATUS', 'port': port}
        self.__socket.send(json.dumps(request).encode('utf-8'))
        # print('{} withFork send {}'.format(self.__address[1], request))
        response = json.loads(self.__socket.recv(1024).decode('utf-8'))
        # print('{} withFork recv'.format(self.__address[1]))
        if response is not None and 'code' in response and response['code'] == 'GET_FORK_STATUS_RESPONSE' and 'withFork' in response:
            # print('{} withFork {}'.format(self.__address[1], response['withFork']))
            return response['withFork'], response['state']
        # print('{} withFork {}'.format(self.__address[1], None))
        return None

    def with_fork(self, port):
        result = self.__get_with_fork_request(port)
        while result is None:
            result = self.__get_with_fork_request(port)
        return result


class Philosopher(Thread):
    WITH_FORK = {}
    STATE = 'THINKING'
    DEADLOCKS = 0

    def __init__(self, port):
        self.__port = port
        self.__manager_client = ManagerClient(self.__port)
        self.__manager_client.start()
        Thread.__init__(self)

        self.__philosopher_server = PhilosopherServer(port)
        self.__philosopher_server.start()
        self.__philosophers = []

        Philosopher.STATE = 'THINKING'
        self.__next_sleeping_time = randint(5, 5000)
        self.__next_thinking_time = randint(5, 5000)

    def run(self):
        print('Waiting be ready')
        while (self.__manager_client.get_pairs() is None) or (not self.__philosopher_server.get_ready()):
            pass
        for p in self.__manager_client.get_pairs():
            Philosopher.WITH_FORK[p] = False

            self.__philosophers.append(PhilosopherClient(p.split(":")[0], int(p.split(':')[1])))

        self.__manager_client.set_ready(True)
        print('Waiting begin')
        while not self.__manager_client.get_begin():
            pass
        while True:
            if Philosopher.STATE == 'THINKING':
                print('Thinking')
                sleep(self.__next_thinking_time / 1000.0)
                self.__next_thinking_time = randint(5, 5000)
                Philosopher.STATE = 'EATING'
            elif Philosopher.STATE == 'EATING':
                print('Trying to eat')
                deadlock = dict([[key, False] for key in Philosopher.WITH_FORK])
                while not reduce((lambda x, y: x and y), Philosopher.WITH_FORK.values()):
                    for p in self.__philosophers:
                        print('Asking fork to {}'.format(p.get_address()))
                        fork_state, philosopher_state = p.with_fork(self.__port)
                        print('{} fork is {} and state is {}'.format(p.get_address(), fork_state, philosopher_state))
                        # print('{} - {}'.format(p.get_address(), fork_state))
                        if fork_state and not Philosopher.WITH_FORK[p.get_address()] and not deadlock[p.get_address()]:
                            deadlock[p.get_address()] = True


                        if not fork_state and not Philosopher.WITH_FORK[p.get_address()]:
                            Philosopher.WITH_FORK[p.get_address()] = True
                print('Eating')
                for p in Philosopher.WITH_FORK:
                    Philosopher.WITH_FORK[p] = False
                print('Going to sleep')

                Philosopher.STATE = 'SLEEPING'
            elif Philosopher.STATE == 'SLEEPING':
                print('Sleeping')
                self.__next_sleeping_time = randint(5, 5000)
                sleep(self.__next_thinking_time / 1000.0)
                Philosopher.STATE = 'THINKING'


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", help="display a square of a given number",
                        type=int)
    args = parser.parse_args()

    philosopher = Philosopher(args.port)
    philosopher.start()