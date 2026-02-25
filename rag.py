import os
import time
from langchain_core.documents import Document 
from langchain_text_splitters import MarkdownTextSplitter
from langchain_community.chat_models import ChatYandexGPT
from langchain_community.embeddings.yandex import YandexGPTEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnablePassthrough, RunnableLambda
from langchain_core.output_parsers import StrOutputParser

YANDEX_API_KEY = ""
YANDEX_FOLDER_ID = ""
MD_FILE_PATH = "Decision_85.md"
DB_FOLDER_PATH = "faiss_decision85"

def clean_text(text):
    if not isinstance(text, str): return text
    return text.encode("utf-8", "ignore").decode("utf-8")

embeddings = YandexGPTEmbeddings(api_key=YANDEX_API_KEY, folder_id=YANDEX_FOLDER_ID)

if os.path.exists(DB_FOLDER_PATH):
    print("Загружаю базу данных...")
    vectorstore = FAISS.load_local(DB_FOLDER_PATH, embeddings, allow_dangerous_deserialization=True)
else:
    print("Создаю базу данных...")
    with open(MD_FILE_PATH, "r", encoding="utf-8", errors="ignore") as f:
        raw_text = clean_text(f.read())
    
    documents = [Document(page_content=raw_text, metadata={"source": MD_FILE_PATH})]
    splitter = MarkdownTextSplitter(chunk_size=1000, chunk_overlap=150)
    chunks = splitter.split_documents(documents)
    
    vectorstore = None
    batch_size = 3
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        if vectorstore is None:
            vectorstore = FAISS.from_documents(batch, embeddings)
        else:
            vectorstore.add_documents(batch)
        time.sleep(1.5)
    vectorstore.save_local(DB_FOLDER_PATH)

retriever = vectorstore.as_retriever(search_kwargs={"k": 4})

llm = ChatYandexGPT(
    api_key=YANDEX_API_KEY, 
    folder_id=YANDEX_FOLDER_ID,
    model_uri=f"gpt://{YANDEX_FOLDER_ID}/yandexgpt/latest",
    temperature=0.1
)

prompt = PromptTemplate.from_template("""Вы — эксперт в медицине и юриспруденции. Отвечайте строго по тексту.
Контекст:
{context}

Вопрос: {question}
Ответ:""")

def format_docs(docs):
    return "\n\n".join(doc.page_content for doc in docs)

def get_answer(input_data):
    question = clean_text(input_data["question"])
    docs = retriever.invoke(question)
    context = format_docs(docs)
    final_prompt = prompt.format(context=context, question=question)
    answer = llm.invoke(final_prompt)
    return {"answer": answer.content, "sources": docs}

if __name__ == "__main__":
    print("\n--- Система готова. Введите вопрос по Решению №85 ---")
    while True:
        try:
            query = input("\nВопрос: ")
            if query.lower() in ['exit', 'quit', 'выход']: break
            
            print("Поиск в документе...")
            result = get_answer({"question": query})
            
            print("\n=== ОТВЕТ ===")
            print(result["answer"])
            
            print("\n--- ИСТОЧНИКИ (фрагменты из Решения №85) ---")
            for i, doc in enumerate(result["sources"]):
                snippet = doc.page_content.replace('\n', ' ')[:250]
                print(f"[{i+1}] {snippet}...")
            print("============================================")
            
        except Exception as e:
            print(f"Ошибка: {e}")