#!/usr/bin/python3
# -*- coding:utf-8 -*-

'worktool第三方问答接口服务的主程序, 连接Rasa rest和worktool的交互'
__author__ = "Paladin"

import json, logging, requests, datetime
from flask import Flask, request, jsonify
import threading
import subprocess

from langchain.document_loaders import DirectoryLoader, TextLoader
from langchain.text_splitter import CharacterTextSplitter
from langchain.embeddings.openai import OpenAIEmbeddings
from langchain.vectorstores import Chroma
import os
import config
os.environ["OPENAI_API_KEY"] = config.configs.get("OPENAI_API_KEY")
os.environ["OPENAI_API_BASE"] = config.configs.get("OPENAI_API_BASE")

# 启动Rasa服务器
def run_rasa():
    # 这行代码将会在新的线程中启动Rasa服务
    # 命令行：rasa run -m models --endpoints endpoints.yml --credentials credentials.yml --port 5005 --enable-api --cors "*" 
    # screen -S s1 -dm rasa run -m models --endpoints endpoints.yml --credentials credentials.yml --port 5005 --enable-api --cors "*" 
    subprocess.run(["rasa", "run", "-m", "models", "--endpoints", "endpoints.yml", 
                    "--credentials", "credentials.yml", "--port", "5005", 
                    "--enable-api", "--cors", "*"])
    
logging.basicConfig(
    filename='./log/app.log',
    level=logging.WARNING,
    format='%(asctime)s %(levelname)s: %(message)s',
    encoding='utf-8'
)
logging.info("info: Flask Web Server is running")
logging.debug("debug testinfo")
logging.warning("warning testinfo")
logging.error("error testinfo")

# 创建Flask应用程序
app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False
app.config['JSONIFY_MIMETYPE'] = "application/json;charset=utf-8"

@app.route('/robotchat', methods=['GET'])
def handle_get_request():
    # pass
    return jsonify({"code": 0, "message": "success"})

@app.route('/robotchat', methods=['POST'])
def handle_post_request():
    try:
        # http://127.0.0.1:5000/robotchat?robotId=b2eed1fbef744cacb7a01c1501431fd21
        '''
        { 
            "spoken": "hi", 
            "rawSpoken": "@me 你好",
            "receivedName": "仑哥",
            "groupName": "测试群1",
            "groupRemark": "测试群1备注名",
            "roomType": 1,
            "atMe": true,
            "textType": 1
        }
        '''
        # 解析请求数据
        data = request.get_json()
       
        # 记录发送的请求数据到文本日志
        log_request_data(data)
        if app.debug:
            print(f"{datetime.datetime.now()} 接到消息：{data}")

        # 获取参数
        robot_id = request.args.get('robotId')
        data["robot_id"] = robot_id
        prompt = data["spoken"]
        if not robot_id or not prompt:
            return jsonify({"code": -1, "message": "error,缺少robotId或prompt"})        
        # 标识一个对话，含robotid、用户名，不包含群名称，这样用户和一个机器人聊天，无论私聊还是多个群聊，都能记住其上下文
        # sender_id = "user-xxx"
        sender_id = f"{data['robot_id']}-*-{data['receivedName']}"

         # 立即返回空回答，实际回答调用异步接口发送
        threading.Thread(target = send_message(sender_id, prompt, data)).start()
         # 构造返回数据
        response_data = {
            "code": 0,
            "message": "success",
            "data": {
                "type": 5000,
                "info": {
                    "text": ""
                }
            }
        }
       
        return jsonify(response_data)        
    except Exception as e:
        logging.error(f"Error handling POST request: {str(e)}")
        return jsonify({"code": -1, "message": "error"})

def send_message(sender_id, prompt, metadata):
    '''子线程中运行。调用worktool的发送指令消息接口，发送Rasa回复，'''

    # 调用 Rasa API 获取回答
    _rasa_answer = get_rasa_answer(sender_id, prompt, metadata)
    # answer = _rasa_answer.json()[0]["text"]
    # rasa返回的消息，是一个list，类型可能有text、image及其他
    if len(_rasa_answer):
        # ralist = [ra["text"] for ra in _rasa_answer]
        # answer = (". ").join(ralist)
        # print(_rasa_answer)
        # logging.info(_rasa_answer)
        for ra in _rasa_answer:
            send_message_toworktool(metadata, ra["text"])
            # print(ra["text"])
        # answer = _rasa_answer[0]["text"]
        # # 调用worktool接口发送指令消息，将ChatGPT的回答发送给用户
        # send_message_toworktool(metadata, answer)

    # 记录接收的请求数据和回答到文本日志
    log_response_data(metadata, _rasa_answer)
    if app.debug:
        print(f"{datetime.datetime.now()} Rasa request：{metadata}")
        print(f"{datetime.datetime.now()} Rasa response：{_rasa_answer}")

def send_message_toworktool(metadata, answer):
    '''
    调用发送消息指令, 给worktool发消息
    '''
    # url = 'https://worktool.asrtts.cn/wework/sendRawMessage'
    url = config.configs.get("worktool")
    headers = {'Content-Type': 'application/json'}
    if metadata:
        robot_id = metadata.get('robot_id')
        if app.debug:
            print("--------------给worktool发送消息：")
            print(f"{datetime.datetime.now()} {robot_id} | {metadata.get('groupName')} | {metadata.get('receivedName')} | {answer}")
        # 企业微信4.08不支持@提问用户，正式运行使用新版企业微信，取消@注释
        payload = {
            "socketType": 2,
            "list": [
                {
                    "type": 203,
                    "titleList": [metadata.get("groupName")],
                    "receivedContent": answer,
                    "atList": [metadata.get("receivedName")]
                }
            ]
        }
        response = requests.post(url, headers=headers, params={'robotId': robot_id}, json=payload)
        response.raise_for_status()
        logging.info(f"{datetime.datetime.now()} 给worktool发送消息：{robot_id} | {metadata.get('groupName')} | {metadata.get('receivedName')} | {answer}")
    else:
        print(f"{datetime.datetime.now()} metadata: {metadata} {answer}")

def get_rasa_answer(sender_id, prompt, data):
    '''请求Rasa回答'''
    # url = 'http://localhost:5005/webhooks/rest/webhook'
    url = config.configs.get("Rasa_api")
    payload = {
        "sender": sender_id,
        'message': prompt,
        "metadata": data
    }
    response = requests.post(url, json = payload)

    response.raise_for_status()
    return response.json()

# def get_sender_id(data):
#     '''组合robot_id、群名称、用户名为sender_id, 用-*-分割'''
#     return f"{data['robot_id']}-*-{data['groupName']}-*-{data['receivedName']}"


def log_request_data(data):
    '''记录请求日志'''
    with open('log/request_log.txt', 'a', encoding='utf-8') as f:
        encoded_data = json.dumps(data, ensure_ascii=False)
        f.write(f"{datetime.datetime.now()} Request Data: {encoded_data}\n")

def log_response_data(data, answer):
    with open('log/response_log.txt', 'a', encoding='utf-8') as f:
        f.write(f"{datetime.datetime.now()} Request Data: {json.dumps(data, ensure_ascii=False)}\n")
        f.write(f"{datetime.datetime.now()} Response Answer: {answer}\n")

def load_embedding():
    '''初始化本地知识库，并 embedding 向量信息持久化存入 Chroma 向量数据库，用于后续匹配查询'''
    # global retriever

    # langchain提供DirectoryLoader方法可直接加载文件夹下指定格式文件
    # loader_kwargs 参数代表是否开启--自动根据编码格式转义
    text_loader_kwargs={'autodetect_encoding': True}
    # 加载文件夹中的所有txt类型的文件
    # loader = DirectoryLoader('./docs/', glob='**/*.txt', loader_cls=TextLoader, loader_kwargs=text_loader_kwargs)
    loader = DirectoryLoader(config.configs.get("kbpath"), glob='**/*.txt')
    # 将数据转成 document 对象，每个文件会作为一个 document
    documents = loader.load()

    # 初始化加载器
    text_splitter = CharacterTextSplitter(chunk_size=200, chunk_overlap=5)
    # 切割加载的 document
    split_docs = text_splitter.split_documents(documents)

    # 初始化 openai 的 embeddings 对象
    embeddings = OpenAIEmbeddings()
    # 将 document 通过 openai 的 embeddings 对象计算 embedding 向量信息并临时存入 Chroma 向量数据库，用于后续匹配查询
    # vectordb = Chroma.from_documents(split_docs, embeddings) # 仅在内存中使用 Chroma 向量数据库，不进行持久化
    # retriever = vectordb.as_retriever(search_kwargs={"k": 5})

    # 持久化数据
    vectordb = Chroma.from_documents(split_docs, embeddings, persist_directory="./vector_store")
    vectordb.persist()
    logging.info("本地知识库成功初始化")
    if app.debug:
        print(f"{datetime.datetime.now()} 本地知识库成功初始化")
    # # 加载数据
    # docsearch = Chroma(persist_directory="./vector_store", embedding_function=embeddings)

    # 仅基于本地向量知识库进行问答
    # 创建问答对象
    # qa = VectorDBQA.from_chain_type(llm=OpenAI(), chain_type="stuff", vectorstore=docsearch,return_source_documents=True)
    # 进行问答
    # result = qa({"query": "什么是多元解纷?"})
    # result = qa({"query": "hi"})

# 启动Flask应用程序
if __name__ == '__main__':
    # 在新的线程中启动Rasa服务
    # threading.Thread(target=run_rasa).start()
    # 初始化本地知识库
    # load_embedding()
    # app.debug = True
    if not app.debug:
        app.run(port=5000)
    else:
        app.run(port=5001)
