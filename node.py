import time,socket,json,random,sys,re,threading
from textwrap import wrap
regex_trgt=("."*48000)+"?"
server=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
try:
    port=int(sys.argv[1])
except:
    port=7777
server.bind(("0.0.0.0",port))

connections={}
memory={}
acks={}
last_uid=0
thread=threading.Thread
readable_buffer={}

def get_id():
    global connections
    i=-1
    while True:
        i+=1
        if i not in connections:
            return i

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
    global connections,memory
    del memory[connections[id]]
    del connections[id]

def required_keys(dict,ins_set):
    for key in ins_set:
        if key not in dict:
            return False
        if type(ins_set[key])!=type(dict[key]):
            return False
    return True

def getch_buffer(id,timeout=None):
    global memory
    if timeout!=None:
        iterations=0
    while len(memory[connections[id]]["buffer"])==0:
        time.sleep(0.01)
        if timeout!=None:
            iterations+=1
            if iterations>timeout:
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
    while True:
        time.sleep(0.25)
        server.sendto(make_msg(json.dumps({"event":"ping","data":"ping"})).encode(),addr)

def client_thread(id):
    thread(target=ping,args=(connections[id],)).start()
    global acks,readable_buffer
    readable_buffer[id]=[]
    data_recvd=[]
    recv_ids=[]
    transfer_mode=False
    recv_mode=False
    current_id=""
    to_recv=0
    recvd_=0
    while True:
        data=(getch_buffer(id,timeout=300))
        if data==False:
            rem_id(id)
            print("client",id,"disconnected")
            exit()
        else:
            is_dict=dict_able(data)
            if is_dict[0]:
                data=is_dict[1]
                if required_keys(data,{"event":"","id":1,"packets":1}) and data["event"]=="send_req" and data["packets"]<1024000:
                    if not transfer_mode and data["id"] in recv_ids:
                        server.sendto(make_msg(json.dumps({"event":"ack","id":data["id"],"data":"ack,"+str(data["id"])})).encode(),connections[id])
                    if transfer_mode and not recv_mode and current_id==data["id"]:
                        server.sendto(make_msg(json.dumps({"event":"ack","id":data["id"],"data":"ack,-1"})).encode(),connections[id])
                    if not transfer_mode and data["id"] not in recv_ids:
                        transfer_mode=True
                        to_recv=data["packets"]
                        recvd_=0
                        data_recvd=[b""]*to_recv
                        current_id=data["id"]
                        recv_ids.append(current_id)
                        if len(recv_ids)>100:
                            recv_ids.remove(recv_ids[0])
                        server.sendto(make_msg(json.dumps({"event":"ack","id":data["id"],"data":"ack,-1"})).encode(),connections[id])
                if transfer_mode and required_keys(data,{"event":"","packet_i":1,"data":"","id":1}) and data["event"]=="data_send":
                    if data["id"]!=current_id and data["id"] in recv_ids:
                        server.sendto(make_msg(json.dumps({"event":"ack","id":data["id"],"data":"ack,"+str(data["packet_i"])})).encode(),connections[id])
                    if data["id"]==current_id and data["packet_i"]<=to_recv and data_recvd[data["packet_i"]]==b"":
                        server.sendto(make_msg(json.dumps({"event":"ack","id":data["id"],"data":"ack,"+str(data["packet_i"])})).encode(),connections[id])
                        data_recvd[data["packet_i"]]=data["data"]
                        recvd_+=1
                        if recvd_==to_recv:
                            transfer_mode=False
                            current_id=""
                            readable_buffer[id].append("".join(data_recvd))
                            print(readable_buffer)
                if required_keys(data,{"event":"","packet_i":1,"data":"","id":1}) and data["event"]=="data_send" and not transfer_mode and data["id"] in recv_ids:
                    server.sendto(make_msg(json.dumps({"event":"ack","id":data["id"],"data":"ack,"+str(data["packet_i"])})).encode(),connections[id])
                if required_keys(data,{"event":"","data":"","id":1}) and data["event"]=="ack" and data["id"] in acks:
                    acks[data["id"]]["acks"].append(int(data["data"].split("ack,")[1]))

def reliable_send(addr,data):
    def get_data(x_data):
        if len(x_data)<=48000:
            return [x_data]
        else:
            return  re.findall(regex_trgt,data)
    data=get_data(data)
    global acks
    id=get_next_uid()
    acks[id]={"acks":[]}
    server.sendto(make_msg(json.dumps({"event":"send_req","packets":len(data),"id":id,"data":""})).encode(),addr)
    iters=0
    while acks[id]["acks"]==[]:
        time.sleep(0.001)
        if iters>10:
            server.sendto(make_msg(json.dumps({"event":"send_req","packets":len(data),"id":id,"data":""})).encode(),addr)
            iters=0
        else:
            iters+=1
    while True:
        next_iter=False
        for x in range(len(data)):
            if x not in acks[id]["acks"]:
                next_iter=True
                server.sendto(make_msg(json.dumps({"event":"data_send","packet_i":x,"id":id,"data":data[x]})).encode(),addr)
        if next_iter:
            time.sleep(0.01)
            continue
        else:
            break

temp_mem={}

def msg_processor(data,addr):
    try:
        data=json.loads(data)
        assert type(data["event"])==type("")
        assert type(data["data"]) in [type(1),type(1.0),type(""),type([]),type({})]
        event=data["event"]
    except:
        return
    if event=="sync" and addr not in connections.values():
        id=get_id()
        connections[id]=addr
        memory[addr]={"buffer":[],"id":id,"thread":thread(target=client_thread,args=(id,))}
        memory[addr]["thread"].start()
        server.sendto(make_msg(json.dumps({"event":"accept","data":""})).encode(),addr)
        print("Client with id",id,"Connected")
    if event=="accept" and addr not in connections.values():
        id=get_id()
        connections[id]=addr
        memory[addr]={"buffer":[],"id":id,"thread":thread(target=client_thread,args=(id,))}
        memory[addr]["thread"].start()
        print("Client with id",id,"Connected")
        server.sendto(make_msg(json.dumps({"event":"ping","data":"ping"})).encode(),addr)
    elif addr in connections.values():
        memory[addr]["buffer"].append(json.dumps(data))

def temp_memory_msg_handler(data,addr):
    global temp_mem
    if addr not in temp_mem:
        temp_mem[addr]=b""
    temp_mem[addr]+=data
    if len(data)>=52000:
        msg_processor(data[:52000],addr)
        temp_mem[addr]=temp_mem[addr][52000:]

def recvr_thread():
    global connections,memory
    while True:
        try:
            data,addr=server.recvfrom(52000)
        except:
            continue
        temp_memory_msg_handler(data,addr)

def sender():
    global connections,memory
    while True:
        data=input(">> ")
        if data=="add":
            try:
                inp_=input("ip:addr >> ").split(":")
                ip_addr=(inp_[0],int(inp_[1]))
                server.sendto(make_msg(json.dumps({"event":"sync","data":""})).encode(),ip_addr)
                print("Connection request sent")
            except:
                import traceback
                traceback.print_exc()
                print("Could not connect to IP:ADDR combination")
        else:
            reliable_send(list(memory.keys())[0],eval(data))

thread(target=recvr_thread).start()
thread(target=sender).start()