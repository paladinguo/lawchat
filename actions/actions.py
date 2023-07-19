import requests, json, logging
from typing import Any, Text, Dict, List
from rasa_sdk import Action, Tracker
from rasa_sdk.events import BotUttered
from rasa_sdk.executor import CollectingDispatcher

from langchain import OpenAI
from langchain.vectorstores import Chroma
from langchain.chat_models import ChatOpenAI
from langchain.embeddings.openai import OpenAIEmbeddings
from langchain.chains.question_answering import load_qa_chain
from langchain.memory import ChatMessageHistory
import os 
import config

logging.basicConfig(
    filename='actions.log',
    level=logging.WARNING,
    format='%(asctime)s %(levelname)s: %(message)s',
    encoding='utf-8'
)

logging.info("info: Rasa Actions Server is running")
logging.debug("debug testinfo")
logging.warning("warning testinfo")
logging.error("error testinfo")

os.environ["OPENAI_API_KEY"] = config.configs.get("OPENAI_API_KEY")
os.environ["OPENAI_API_BASE"] = config.configs.get("OPENAI_API_BASE")

class ActionChatGPT(Action):
    def name(self) -> Text:
        return "action_fallback_gpt"

    async def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        # 上下文历史记录
        # messages": [{"role": "system", "content": "You are a helpful assistant."}, {"role": "user", "content": "Hello!"}, {"role": "assistant", "content": "hi,i am ai!"}]
        # user_utterances = [e['text'] for e in tracker.events if e['event'] == 'user' or e['event'] == 'bot']
        # context = ". ".join(user_utterances)  

        # --使用metadata中的数据进行逻辑处理
        # 可以通过请求rasa rest时随message附带metadata，传入自定义数据供action处理业务逻辑使用
        print("\r\n--------------")
        print(tracker.latest_message)
        logging.info(tracker.latest_message)
        metadata = tracker.latest_message.get('metadata')
        # print(f"metadata: {tracker.latest_message.get('metadata')}")
        sender_id = tracker.sender_id

        # 调用ChatGPT回答，处理上下文历史记录！
        # 过滤出 event 值为 'bot' 或 'user' 的事件,取倒数最多10个
        filtered_events = [event for event in tracker.events if event.get("event") in ['bot', 'user']][-10:]
        # 创建 OpenAI 消息列表
        openai_messages = [
            {"role": "system", "content": """你的角色是一个中国的律师AI问答助手，名叫包晴天，不用告诉用户你的角色，只回答名字。
            请用最简洁的语言、最少的字数模拟和人类对话，不要做过多的分析、展开阐述缘由，不是法律问题也可以回答。"""},
            {"role": "system", "content": """回答问题需基于中国现行法律，有必要可引用法条。
            如果用户需要咨询律师或写法律文书，推荐律所电话15011991188 或  #公众号:快法 ；"""}
        ]
        for event in filtered_events:
            if event:
                if event['event'] == 'bot' and event.get("text") != None:
                    openai_messages.append({"role": "assistant", "content": event.get("text")})
                elif event['event'] == 'user' and event.get("text") != None:
                    openai_messages.append({"role": "user", "content":  event.get("text")})

        print("--------------GPT消息：")
        print(openai_messages)
        logging.info(openai_messages)
        # 调用OpenAI回答
        # answer = await get_openai_answer(openai_messages)
        # 调用Langchain回答
        answer = await get_langchain_answer(tracker.latest_message.get("text"), openai_messages)
        # answer = "gpt answer"
        print(f"sender_id: {sender_id} | Langchain answer: {answer}")
        logging.info(f"sender_id: {sender_id} | Langchain answer: {answer}")

        # dispatcher.utter_message("test")
        return [BotUttered(text = answer)]
    

async def get_langchain_answer(query, openai_messages):
    # 使用ChatOpenAI接口
    llm = ChatOpenAI(temperature=0.7, verbose=True)
    # 初始化 openai 的 embeddings 对象
    embeddings = OpenAIEmbeddings()
    # 初始化 MessageHistory 对象
    history = ChatMessageHistory()

    # 给 MessageHistory 对象添加对话内容
    # history.add_ai_message("你好！")
    # history.add_user_message("中国的首都是哪里？")
    for m in openai_messages:
        if m['role'] == 'user' or m['role'] == 'system':
            history.add_user_message(m["content"])
        else:
            history.add_ai_message(m["content"])

    # 加载数据
    vectordb = Chroma(persist_directory="./vector_store", embedding_function=embeddings)
    retriever = vectordb.as_retriever(search_kwargs={"k": 5})

    relevantDocs = retriever.get_relevant_documents(query)
    chain = load_qa_chain(llm, chain_type="stuff")
    result = chain({"input_documents": relevantDocs, "question": history.messages}, return_only_outputs=True)

    return result['output_text']


