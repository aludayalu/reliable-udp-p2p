import time,socket,json,uuid,sys,threading,traceback
from itertools import zip_longest
try:
    port=int(sys.argv[1])
except:
    port=7777

connections={}
memory={}
acks={}
last_uid=0
thread=threading.Thread
readable_buffer={}
counter=0
debug_mode=False
status={}

def send(data,addr,recursions=0):
    if recursions==10:
        if debug_mode:
            print("Conman: Unable to write buffer after 10 retries")
        return
    try:
        server.sendto(data,addr)
    except:
        traceback.print_exc()
        time.sleep(0.1)
        send(data,addr,recursions+1)

def get_id():
    global counter
    counter+=1
    return counter

def grouper(iterable, n, fillvalue=None):
    args = [iter(iterable)] * n
    return zip_longest(*args, fillvalue=fillvalue)

def data_splitter(data,n):
    resp=list(grouper(data,n))
    out=[]
    for x in resp:
        out.append("".join([y for y in x if y!=None]))
    return out

def get_next_uid():
    global last_uid
    if last_uid>1000000:
        last_uid=0
    last_uid+=1
    return last_uid

def make_msg(data):
    if len(data)<52000:
        data=data+" "*(52000-len(data))
    return data

def rem_id(id):
    global connections,memory,readable_buffer
    del memory[connections[id]]
    del connections[id]
    del readable_buffer[id]

def required_keys(dict,ins_set):
    for key in ins_set:
        if key not in dict:
            return False
        if type(ins_set[key])!=type(dict[key]):
            return False
    return True

def getch_buffer(id,timeout=None):
    global memory,status
    if timeout!=None:
        iterations=0
    try:
        while status[id] and len(memory[connections[id]]["buffer"])==0:
            if readable_buffer[id]["connected"]==False:
                return False
            time.sleep(0.01)
            if timeout!=None:
                iterations+=1
                if iterations>timeout:
                    return False
        if not status[id]:
            return False
    except:
        return False
    resp=memory[connections[id]]["buffer"][0]
    memory[connections[id]]["buffer"].remove(memory[connections[id]]["buffer"][0])
    return resp

def dict_able(data):
    try:
        res=True,json.loads(data)
        return res
    except:
        return False,False

def ping(addr):
    while addr in memory:
        time.sleep(0.3)
        send(make_msg(json.dumps({"event":"ping","data":"ping"})).encode(),addr)

def client_thread(id):
    global acks,readable_buffer,status
    if id not in readable_buffer:
        globals()['readable_buffer'][id]={"read":[],"write":[],"connected":True}
    thread(target=ping,args=(connections[id],)).start()
    data_recvd=[]
    recv_ids=[]
    transfer_mode=False
    recv_mode=False
    current_id=""
    to_recv=0
    recvd_=0
    while status[id]:
        try:
            data=(getch_buffer(id,timeout=300))
        except:
            return
        if data==False:
            rem_id(id)
            return
        else:
            is_dict=dict_able(data)
            if is_dict[0]:
                data=is_dict[1]
                if required_keys(data,{"event":"","id":1,"packets":1}) and data["event"]=="send_req" and data["packets"]<1024000:
                    if debug_mode:
                        print("Conman: New send Request")
                    if not transfer_mode and data["id"] in recv_ids:
                        send(make_msg(json.dumps({"event":"ack","id":data["id"],"data":"ack,"+str(data["id"])})).encode(),connections[id])
                    if transfer_mode and not recv_mode and current_id==data["id"]:
                        send(make_msg(json.dumps({"event":"ack","id":data["id"],"data":"ack,-1"})).encode(),connections[id])
                    if not transfer_mode and data["id"] not in recv_ids:
                        transfer_mode=True
                        to_recv=data["packets"]
                        recvd_=0
                        data_recvd=[b""]*to_recv
                        current_id=data["id"]
                        recv_ids.append(current_id)
                        if len(recv_ids)>100:
                            recv_ids.remove(recv_ids[0])
                        send(make_msg(json.dumps({"event":"ack","id":data["id"],"data":"ack,-1"})).encode(),connections[id])
                if transfer_mode and required_keys(data,{"event":"","packet_i":1,"data":"","id":1}) and data["event"]=="data_send":
                    if debug_mode:
                        print(f"Conman: Data packet {data['packet_i']} received")
                    if data["id"]!=current_id and data["id"] in recv_ids:
                        send(make_msg(json.dumps({"event":"ack","id":data["id"],"data":"ack,"+str(data["packet_i"])})).encode(),connections[id])
                    if data["id"]==current_id and data["packet_i"]<=to_recv and data_recvd[data["packet_i"]]==b"":
                        send(make_msg(json.dumps({"event":"ack","id":data["id"],"data":"ack,"+str(data["packet_i"])})).encode(),connections[id])
                        data_recvd[data["packet_i"]]=data["data"]
                        recvd_+=1
                        if recvd_==to_recv:
                            transfer_mode=False
                            current_id=""
                            readable_buffer[id]["read"].append("".join(data_recvd))
                if required_keys(data,{"event":"","packet_i":1,"data":"","id":1}) and data["event"]=="data_send" and not transfer_mode and data["id"] in recv_ids:
                    if debug_mode:
                        print("Conman: Ack Sent")
                    send(make_msg(json.dumps({"event":"ack","id":data["id"],"data":"ack,"+str(data["packet_i"])})).encode(),connections[id])
                if required_keys(data,{"event":"","data":"","id":1}) and data["event"]=="ack" and data["id"] in acks:
                    if debug_mode:
                        print("Conman: Ack Received")
                    acks[data["id"]]["acks"].append(int(data["data"].split("ack,")[1]))
    return

def reliable_send(addr,data):
    global status
    if debug_mode:
        print("Conman: Data Send Request")
    data=data_splitter(data,48000)
    global acks
    id=get_next_uid()
    acks[id]={"acks":[]}
    send(make_msg(json.dumps({"event":"send_req","packets":len(data),"id":id,"data":""})).encode(),addr)
    iters=0
    if debug_mode:
        print("Conman: Waiting For Ack")
    while status[addr]==True and acks[id]["acks"]==[]:
        time.sleep(0.001)
        if iters>10:
            send(make_msg(json.dumps({"event":"send_req","packets":len(data),"id":id,"data":""})).encode(),addr)
            iters=0
        else:
            iters+=1
    if status[addr]==False:
        return False
    if debug_mode:
        print("Conman: Initial Ack Received. Sending Data")
    iters=0
    last_state=acks[id]["acks"]
    while True:
        current_state=acks[id]["acks"]
        if current_state==last_state:
            iters+=1
        else:
            iters=0
        if iters>300:
            return False
        last_state=acks[id]["acks"]
        next_iter=False
        for x in range(len(data)):
            if x not in acks[id]["acks"]:
                next_iter=True
                send(make_msg(json.dumps({"event":"data_send","packet_i":x,"id":id,"data":data[x]})).encode(),addr)
        if next_iter:
            time.sleep(0.01)
            continue
        else:
            break
    if debug_mode:
        print("Conman: All Data Sent")
    return True

temp_mem={}

def msg_processor(data,addr,client_handler):
    global status
    try:
        data=json.loads(data)
        assert type(data["event"])==type("")
        assert type(data["data"]) in [type(1),type(1.0),type(""),type([]),type({})]
        event=data["event"]
    except:
        return
    if event=="sync" and addr in connections.values():
        send(make_msg(json.dumps({"event":"accept","data":""})).encode(),addr)
    elif event=="sync" and addr not in connections.values():
        id=addr
        status[id]=True
        connections[id]=addr
        memory[addr]={"buffer":[],"conn_obj":"","id":id,"thread":thread(target=client_thread,args=(id,))}
        memory[addr]["conn_obj"]=connection_class(addr)
        memory[addr]["thread"].start()
        send(make_msg(json.dumps({"event":"accept","data":""})).encode(),addr)
        thread(target=client_handler,args=(memory[addr]["conn_obj"],)).start()
    elif event=="accept" and addr not in connections.values():
        id=addr
        connections[id]=addr
        status[id]=True
        memory[addr]={"buffer":[],"conn_obj":"","id":id,"thread":thread(target=client_thread,args=(id,))}
        memory[addr]["conn_obj"]=connection_class(addr)
        memory[addr]["thread"].start()
        thread(target=client_handler,args=(memory[addr]["conn_obj"],)).start()
        send(make_msg(json.dumps({"event":"ping","data":"ping"})).encode(),addr)
    elif addr in connections.values():
        memory[addr]["buffer"].append(json.dumps(data))

def recvr_thread(client_handler):
    global connections,memory,temp_mem
    while True:
        try:
            data,addr=server.recvfrom(52000)
        except:
            continue
        if addr not in temp_mem:
            temp_mem[addr]=b""
        temp_mem[addr]+=data
        if len(data)>=52000:
            msg_processor(data[:52000],addr,client_handler)
            temp_mem[addr]=temp_mem[addr][52000:]

def writer():
    global readable_buffer
    while True:
        time.sleep(0.01)
        for x in readable_buffer.copy():
            try:
                _key_=x
                x=readable_buffer[x]
                if x["write"]!=[]:
                    thread(target=reliable_send,args=(connections[_key_],x["write"][0])).start()
                    del readable_buffer[_key_]["write"][0]
            except:
                import traceback
                traceback.print_exc()

def connection(addr):
    if addr in memory:
        return memory[addr]["conn_obj"]
    else:
        if str(get_connection(addr))==str(False):
            return False
        return memory[addr]["conn_obj"]

class msg:
    def __init__(self,event,data,uid) -> None:
        self.event=event
        self.data=data
        self.uid=uid

def connection_listener(conn):
    while True:
        data=conn.recv(json_=False)
        if data==False:
            return
        try:
            data=json.loads(data)
            if type(data)==type({}) and "event" in data and "data" in data and "uid" in data:
                if data["event"] in conn.events:
                    _data_=conn.events["on_recv"](msg(data["event"],data["data"],data["uid"]))
                    if _data_!=None and _data_!=False:
                        if debug_mode:
                            print(f"Conman: Triggering Event {data['event']}")
                        conn.events[data["event"]](_data_,conn)
        except:
            import traceback
            traceback.print_exc()
            conn.temp={}
            continue

class connection_class:
    def __init__(self,addr):
        self.id=get_connection(addr)
        self.events={"close":lambda x:print("Client with id",x.id,"Disconnected"),"on_recv":lambda x:x}
        self.temp={}
        self.last_activity=time.time()
        if str(self.id)==str(False):
            raise Exception("Connection Closed")
        thread(target=connection_listener,args=(self,)).start()
    def send(self,event,data,uid=None):
        self.last_activity=time.time()
        global readable_buffer
        if self.id not in connections:
            self.close()
        if uid==None:
            uid=str(uuid.uuid4())
        if type(data) in [type(""),type([]),type(1),type(1.0),type({})]:
            pass
        else:
            return False
        data=json.dumps({"event":event,"data":data,"uid":uid})
        if self.id not in readable_buffer:
            readable_buffer[self.id]={"read":[],"write":[]}
        readable_buffer[self.id]["write"].append(data)
    def recv(self,json_=True):
        self.last_activity=time.time()
        time.sleep(0.001)
        global readable_buffer
        if self.id not in connections:
            self.close()
        while True:
            try:
                while readable_buffer[self.id]["read"]==[]:
                    time.sleep(0.01)
                    pass
            except:
                self.close()
            res=readable_buffer[self.id]["read"][0]
            del readable_buffer[self.id]["read"][0]
            self.last_activity=time.time()
            if json_:
                res_=dict_able(res)
                if res_[0]:
                    try:
                        if debug_mode:
                            print(f"Conman: JSON {self.id} Returned")
                        return msg(res_[1]["event"],res_[1]["data"],res_[1]["uid"])
                    except:
                        if debug_mode:
                            print(f"Conman: Not Valid JSON {self.id} Continued")
                        continue
            else:
                if debug_mode:
                    print(f"Conman: Not JSON {self.id} Returned")
                return res
    def link_event(self,event,func):
        self.last_activity=time.time()
        if self.id not in connections:
            return False
        self.events[event]=func
    def unlink_event(self,event,func):
        self.last_activity=time.time()
        if self.id not in connections:
            return False
        try:
            del self.events[event]
        except:
            return False
    def close(self):
        self.last_activity=time.time()
        globals()["close"](self.id,True)
        self.events["close"](self)
        raise Exception("Connection Closed")

def close(id,del_=False):
    global status
    status[id]=False
    if del_:
        del status[id]

def get_connection(addr:tuple):
    if addr in memory:
        return memory[addr]["id"]
    send(make_msg(json.dumps({"event":"sync","data":""})).encode(),addr)
    for x in range(30):
        if addr in memory:
            return memory[addr]["id"]
        time.sleep(0.1)
        send(make_msg(json.dumps({"event":"sync","data":""})).encode(),addr)
    return False

def clear_buffer(id,read=True,write=True):
    global readable_buffer
    if id in readable_buffer:
        readable_buffer[id]={"read":[] if read else readable_buffer[id]["read"],"write":[] if write else readable_buffer[id]["write"],"connected":True}

def node(addr,client_handler):
    global server
    server=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    server.bind(addr)
    thread(target=recvr_thread,args=(client_handler,)).start()
    thread(target=writer).start()
if __name__=="__main__":
    node(("0.0.0.0",port),lambda x:print("Client with",x.id,"has Connected"))