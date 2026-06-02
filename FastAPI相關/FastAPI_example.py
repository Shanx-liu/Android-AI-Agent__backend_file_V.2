from fastapi import FastAPI, Path, Query
import uvicorn
from enum import Enum
from typing import Optional
from pydantic import BaseModel

app = FastAPI()

@app.get('/')       #定義網址後面接的路徑參數 '/' 為根
async def helloworld():     #此網址+路徑參數的處理函式
    return{"messages": "Hello world"}


@app.get('/user/current')       #路徑參數判斷順序很重要，此例需在user_id前
async def current_user():       #小範圍在前，大範圍在後
    return{"This is current user"}


@app.get('/user/{user_id}')     #路徑參數範例
async def get_user(user_id: int):    #URL裡的變數名稱一定要跟函式參數名稱一樣
    return{f"This is user id for {user_id}"}

#--------------------------------------------------------------------------------

class Gender(str, Enum):    #自定義的枚舉類別
    male = 'male'          #後面的字串為URL要輸入的字串
    female = 'female'

@app.get('/student/{gender}')       #將參數設為枚舉類型
async def student_gender(gender: Gender):
    return{"student": f"This is a {gender.value} student"}

#--------------------------------------------------------------------------------

@app.get('/users')      #路徑查詢參數，第二個參數具默認值，參數沒有在查詢路徑中就是查詢參數
async def get_users(page_index: int, page_size: Optional[int] = 10):
    return{"page info": f"page_index: {page_index}, page_size: {page_size}"}


@app.get('/user/{user_id}/friends')      #底下方法中參數位置不必照順序
async def get_user_friends(page_index: int, user_id: int, page_size: Optional[int] = 10):
    return{"user friends": f"user_id: {user_id}, page_index: {page_index}, page_size: {page_size}"}

#--------------------------------------------------------------------------------

class UserModel(BaseModel):         #定義一個接收類型
    username: str
    description: Optional[str] = "default"
    gender: Gender

@app.post('/users')         #設定一個接收客戶資料的API
async def create_user(user_model: UserModel):
    print(user_model.username)
    user_dict = user_model.model_dump()     #將接收的參數轉換為dict格式(即JSON)
    
    return user_dict        #轉為dict之後才能回傳

#-----------------------------------------------------------------------------

@app.put('/user/{user_id}')     #更新使用者資料，使用PUT請求
async def update_user(user_id: int, user_model: UserModel):
    print(user_model.username ,user_id)
    user_dict = user_model.model_dump()
    user_dict.update({"user_id": user_id})      #將user_id加進返回的dict中
    return user_dict

#函數的參數識別規則
"""
1. 如果在路徑參數中定義了，那麼匹配為查詢參數
2. 如果參數的類型為int、str等基本類型 , 則為查詢參數
3. 如果是pydantic的模型類型 , 則為請求體
"""

#-----------------------------------------------------------------------------

@app.get('/users/{user_id}')    #請求體的參數驗證，使用Path類別
async def get_user(user_id: int = Path(..., title="USER ID", ge=1, le=1000)):
    return{f"This user id = {user_id}"}     #省略號為此變數必填

@app.get('/books/{book_name}')
async def get_book(book_name: str = Path(..., title="BOOK NAME", min_length=3, max_length=100)):
    return{f"This book name is {book_name}"}

@app.get('/books/{item_num}')       #使用正則表達式驗證 a-78568
async def get_item(item_num: str = Path(..., title="ITEM NUMBER", regex='^[a|b|c]-[\\d]*$')):
    return{f"This item number is {item_num}"}

@app.get('/users')      #使用查詢參數驗證，用Query，第一個參數可填預設值
async def get_page(page_index: int = Query(1, title="PAGE", ge=1, le=100)):
    return{f"This page index is {page_index}"}

#--------------------------------------------------------------------------------
if __name__ == '__main__':      #一鍵啟動伺服器
    uvicorn.run("FastAPI_example:app", port=8001, reload=True)