# Reliable UDP P2P In Python
## Basic Usage
Echo Server
```python
from node import *
def client_thread(conn):
    print("Client with id",conn.id,"has connected")
    def echo(conn,data):
        conn.send(data.event,data.data)
    conn.link_event("echo",echo)
node(("127.0.0.1",1),client_thread)
```
Client
```python
from node import *
def client_thread(conn):
    print("Client with id",conn.id,"has connected")
    def echo(conn,data):
        print(data.data)
    conn.link_event("echo",echo)
node(("0.0.0.0",7777),client_thread)
conn=connect(("127.0.0.1",1))
def sender():
    while True:
        conn.send("echo",input(">> "))
thread(target=sender).start()
```