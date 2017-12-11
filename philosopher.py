import argparse
import json
import socket
from functools import reduce
from threading import Thread
from multiprocessing import Queue
from random import randint
from time import sleep


class ManagerClient(Thread):
    def __init__(self, manager_address, port):
        self.__socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.__killme = False
        self.__port = port
        self.__ready = False
        self.__pairs = None
        self.__begin = False
        self.__manager_address = manager_address

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
        self.__socket.connect(self.__manager_address)
        while not Philosopher.TIME_TO_DIE:
            request = json.loads(self.__socket.recv(1024).decode('utf-8'))
            if request is not None:
                if 'code' in request:
                    if request['code'] == 'GET_PORT':
                        self.__socket.send(json.dumps({'code': 'GET_PORT_RESPONSE',
                                                       'port': self.__port}).encode('utf-8'))
                    elif request['code'] == 'POST_PAIRS' and 'pairs' in request and 'mode' in request:
                        self.__pairs = request['pairs']
                        if 'first' in request:
                            Philosopher.TOKEN = (True, request['first'])

                        Philosopher.WITH_TOKEN = request['mode'] == 'TOKEN'

                        self.__socket.send(json.dumps({'code': 'POST_PAIR_RESPONSE'}).encode('utf-8'))
                    elif request['code'] == 'GET_READY':
                        self.__socket.send(
                            json.dumps({'code': 'GET_READY_RESPONSE', 'ready': self.__ready}).encode('utf-8'))
                    elif request['code'] == 'POST_BEGIN':
                        self.__begin = True
                        self.__socket.send(json.dumps({'code': 'BEGIN_RESPONSE'}).encode('utf-8'))
                    elif request['code'] == 'GET_STATUS_INFO':
                        self.__socket.send(json.dumps({'code': 'GET_STATUS_INFO_RESPONSE',
                                                       'token': Philosopher.TOKEN,
                                                       'deadlocks': Philosopher.DEADLOCKS,
                                                       'meals': Philosopher.MEALS,
                                                       'messagesSent': Philosopher.MESSAGES_SENT,
                                                       'messagesReceived': Philosopher.MESSAGES_RECEIVED
                                                       }).encode('utf-8'))
                    elif request['code'] == 'TIME_TO_DIE':
                        self.__socket.send(json.dumps({'code': 'FINALLY_DEAD_RESPONSE',
                                                       'token': Philosopher.TOKEN,
                                                       'deadlocks': Philosopher.DEADLOCKS,
                                                       'meals': Philosopher.MEALS,
                                                       'messagesSent': Philosopher.MESSAGES_SENT,
                                                       'messagesReceived': Philosopher.MESSAGES_RECEIVED
                                                       }).encode('utf-8'))
                        Philosopher.TIME_TO_DIE = True

        self.__socket.close()


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
        while not Philosopher.TIME_TO_DIE:
            request = json.loads(self.__socket.recv(1024).decode('utf-8'))
            Philosopher.MESSAGES_RECEIVED += 1
            if request is not None:
                if 'code' in request:
                    # print('req {}'.format(request))
                    if request['code'] == 'GET_FORK_STATUS' and 'port' in request and request['port'] is not None:
                        response = {'code': 'GET_FORK_STATUS_RESPONSE',
                                    'withFork': Philosopher.WITH_FORK['{}:{}'.format(self.__address, request['port'])],
                                    'state': Philosopher.STATE}
                        Philosopher.MESSAGES_SENT += 1
                        self.__socket.send(json.dumps(response).encode('utf-8'))
                    if request['code'] == 'POST_TOKEN' and 'port' in request and request['port'] is not None:
                        plist = list(Philosopher.WITH_FORK.keys())
                        plist.remove('{}:{}'.format(self.__address, request['port']))
                        destination = plist[0]
                        Philosopher.TOKEN = (True, destination)
                        response = {'code': 'POST_TOKEN_RESPONSE'}
                        Philosopher.MESSAGES_SENT += 1
                        self.__socket.send(json.dumps(response).encode('utf-8'))

        self.__socket.close()


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
        while not Philosopher.TIME_TO_DIE:
            self.__ready = True
            con, cliente = self.__socket.accept()
            self.__connections.append(PhilosopherServerConnection(len(self.__connections), con, cliente))
            self.__connections[-1].start()

        self.__socket.close()


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
        Philosopher.MESSAGES_SENT += 1
        self.__socket.send(json.dumps(request).encode('utf-8'))
        # print('{} withFork send {}'.format(self.__address[1], request))
        response = json.loads(self.__socket.recv(1024).decode('utf-8'))
        Philosopher.MESSAGES_RECEIVED += 1
        # print('{} withFork recv'.format(self.__address[1]))
        if response is not None and 'code' in response and response[
            'code'] == 'GET_FORK_STATUS_RESPONSE' and 'withFork' in response:
            return response['withFork'], response['state']
        return None

    def __pass_token_request(self, port):
        request = {'code': 'POST_TOKEN', 'port': port}
        self.__socket.send(json.dumps(request).encode('utf-8'))
        Philosopher.MESSAGES_SENT += 1
        response = json.loads(self.__socket.recv(1024).decode('utf-8'))
        Philosopher.MESSAGES_RECEIVED += 1
        if response is not None and 'code' in response and response['code'] == 'POST_TOKEN_RESPONSE':
            return True
        return None

    def with_fork(self, port):
        result = self.__get_with_fork_request(port)
        while result is None:
            result = self.__get_with_fork_request(port)
        return result

    def pass_token(self, port):
        while self.__pass_token_request(port) is None:
            pass


class Philosopher(Thread):
    WITH_FORK = {}
    TOKEN = (False, "")
    STATE = 'THINKING'
    DEADLOCKS = 0
    MEALS = 0
    TIME_TO_DIE = False
    MESSAGES_RECEIVED = 0
    MESSAGES_SENT = 0

    WITH_TOKEN = True

    def __init__(self, manager_address, port):
        self.__port = port
        self.__manager_client = ManagerClient(manager_address, self.__port)
        self.__manager_client.start()
        Thread.__init__(self)

        self.__philosopher_server = PhilosopherServer(port)
        self.__philosopher_server.start()
        self.__philosophers = {}

        self.__min_time = 5
        self.__max_time = 50

        Philosopher.STATE = 'THINKING'
        self.__next_sleeping_time = randint(self.__min_time, self.__max_time)
        self.__next_thinking_time = randint(self.__min_time, self.__max_time)

    def run(self):
        print('Waiting be ready')
        while (self.__manager_client.get_pairs() is None) or (not self.__philosopher_server.get_ready()):
            pass
        for p in self.__manager_client.get_pairs():
            Philosopher.WITH_FORK[p] = False
            self.__philosophers[p] = PhilosopherClient(p.split(":")[0], int(p.split(':')[1]))

        self.__manager_client.set_ready(True)
        print('Waiting begin')
        while not self.__manager_client.get_begin():
            pass
        while not Philosopher.TIME_TO_DIE:
            if Philosopher.STATE == 'THINKING':
                print('Thinking')
                sleep(self.__next_thinking_time / 1000.0)
                self.__next_thinking_time = randint(self.__min_time, self.__max_time)
                Philosopher.STATE = 'EATING'
            elif Philosopher.STATE == 'EATING':
                print('Trying to eat')
                deadlock = dict([[key, False] for key in Philosopher.WITH_FORK])
                for p in self.__philosophers.values():
                    print('Asking fork to {}'.format(p.get_address()))
                    fork_state, philosopher_state = p.with_fork(self.__port)
                    print('{} fork is {} and state is {}'.format(p.get_address(), fork_state, philosopher_state))
                    # print('{} - {}'.format(p.get_address(), fork_state))
                    if fork_state and not Philosopher.WITH_FORK[p.get_address()] and not deadlock[p.get_address()] and \
                            (Philosopher.TOKEN[0] or not Philosopher.WITH_TOKEN):
                        deadlock[p.get_address()] = True
                        Philosopher.DEADLOCKS += 1
                    if not fork_state and not Philosopher.WITH_FORK[p.get_address()] and (Philosopher.TOKEN[0] or not Philosopher.WITH_TOKEN):
                        Philosopher.WITH_FORK[p.get_address()] = True

                if reduce((lambda x, y: x and y), Philosopher.WITH_FORK.values()) and (Philosopher.TOKEN[0] or not Philosopher.WITH_TOKEN):
                    Philosopher.MEALS += 1
                    print('Eating')
                    for p in Philosopher.WITH_FORK:
                        Philosopher.WITH_FORK[p] = False

                    if Philosopher.WITH_TOKEN:
                        self.__philosophers[Philosopher.TOKEN[1]].pass_token(self.__port)
                    Philosopher.TOKEN = (False, "")

                print('Going to sleep')
                Philosopher.STATE = 'SLEEPING'

                # while not reduce((lambda x, y: x and y), Philosopher.WITH_FORK.values()):
                #     for p in self.__philosophers:
                #         print('Asking fork to {}'.format(p.get_address()))
                #         fork_state, philosopher_state = p.with_fork(self.__port)
                #         print('{} fork is {} and state is {}'.format(p.get_address(), fork_state, philosopher_state))
                #         # print('{} - {}'.format(p.get_address(), fork_state))
                #         if fork_state and not Philosopher.WITH_FORK[p.get_address()] and not deadlock[p.get_address()]:
                #             deadlock[p.get_address()] = True
                #             Philosopher.DEADLOCKS += 1
                #         if not fork_state and not Philosopher.WITH_FORK[p.get_address()]:
                #             Philosopher.WITH_FORK[p.get_address()] = True


            elif Philosopher.STATE == 'SLEEPING':
                print('Sleeping')
                self.__next_sleeping_time = randint(self.__min_time, self.__max_time)
                sleep(self.__next_thinking_time / 1000.0)
                Philosopher.STATE = 'THINKING'


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", help="application port",
                        type=int)
    parser.add_argument('--manager', help="manager address", type=str)

    args = parser.parse_args()

    manager_address = (args.manager.split(':')[0], int(args.manager.split(':')[1]))
    philosopher = Philosopher(manager_address, args.port)
    philosopher.start()
    philosopher.join()

    print('I am dead')
