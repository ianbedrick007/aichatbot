from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, Request, HTTPException, status, Depends, Query
from fastapi import Form
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException
from werkzeug.security import generate_password_hash, check_password_hash

from ai.run_ai import get_ai_response, update_conversation_history, get_conversation_history
from auth import create_access_token
from database import get_db, engine, get_current_user
from models import Business
from models import User, Base, Message, Product
from routers import products, users
from schemas import ProductResponse
# Import WhatsApp bot router
from whatsapp_bot.app import router as whatsapp_router, configure_logging
from whatsapp_bot.app.utils.whatsapp_utils import toggle_ai_status, get_text_message_input, send_message, AI_DISABLED_USERS


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Startup
    Base.metadata.create_all(bind=engine)
    configure_logging()  # Configure WhatsApp bot logging
    yield


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/media", StaticFiles(directory="media"), name="media")

print("--- Loading main.py application ---")

templates = Jinja2Templates(directory="templates")

# Include routers
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(products.router, prefix="", tags=["posts"])
app.include_router(whatsapp_router, prefix="/api/whatsapp", tags=["whatsapp"])


@app.get("/", include_in_schema=False, name="home")
def chat_page(
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    # Fetch business for this user
    business = db.execute(
        select(Business).where(Business.user_id == current_user.id)
    ).scalar()

    if not business:
        response = RedirectResponse(url="/logout", status_code=303)
        response.set_cookie("error", "No business found for this account.")
        return response

    return templates.TemplateResponse(
        "chat.html",
        {"request": request, "business": business}
    )


@app.post("/", include_in_schema=False)
async def chat_post(
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
        message: str = Form(...)
):
    # Fetch business
    business = db.execute(
        select(Business).where(Business.user_id == current_user.id)
    ).scalar()

    if not business:
        response = RedirectResponse(url="/logout", status_code=303)
        response.set_cookie("error", "No business found for this account.")
        return response

    user_message = message.strip()

    if user_message:
        # Get last 20 messages for context (isolated by username for web chat)
        recent_messages = get_conversation_history(
            business_id=business.id, 
            customer_id=current_user.username, 
            db=db
        )

        # Get AI response
        bot_response = get_ai_response(
            user_input=user_message,
            db=db,
            conversation_history=recent_messages,
            business_id=business.id,
            user_name=current_user.username
        )

        # Save user message
        update_conversation_history(
            db=db, 
            business_id=business.id, 
            text=user_message, 
            sender=current_user.username,
            customer_id=current_user.username,
            customer_name=current_user.username,
            is_bot=False,
            platform="web"
        )

        # Save bot response
        update_conversation_history(
            db=db, 
            business_id=business.id, 
            text=bot_response, 
            sender="bot",
            customer_id=current_user.username,
            customer_name=current_user.username,
            is_bot=True,
            platform="web"
        )

    return RedirectResponse(url="/", status_code=303)


class ChatRequest(BaseModel):
    message: str


@app.get("/conversations", name="conversations")
def conversations_page(
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    business = db.execute(select(Business).where(Business.user_id == current_user.id)).scalar()
    if not business:
        return RedirectResponse(url="/", status_code=303)

    return templates.TemplateResponse(
        "conversations.html",
        {"request": request, "business": business}
    )


@app.get("/api/live-messages")
def get_live_messages(
        request: Request,
        after_id: int = Query(0),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    business = db.execute(select(Business).where(Business.user_id == current_user.id)).scalar()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    # ✅ Fetch only WHATSAPP messages newer than 'after_id'
    new_messages = (
        db.query(Message)
        .filter(Message.business_id == business.id)
        .filter(Message.id > after_id)
        .filter(Message.platform == 'whatsapp')  # <--- STRICT FILTER
        .order_by(Message.id.asc())
        .limit(50)
        .all()
    )

    return {
        "messages": [
            {
                "id": msg.id,
                "text": msg.text,
                "sender": msg.sender,
                "timestamp": msg.timestamp.strftime("%H:%M"),
                "is_bot": msg.sender == 'bot'
            }
            for msg in new_messages
        ]
    }


@app.get("/api/customers", tags=["conversations"])
def get_customers_list(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """Get list of unique WhatsApp customers with their latest messages"""
    business = db.execute(select(Business).where(Business.user_id == current_user.id)).scalar()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    # Get all WhatsApp messages for this business
    whatsapp_messages = (
        db.query(Message)
        .filter(Message.business_id == business.id)
        .filter(Message.platform == 'whatsapp')
        .order_by(Message.timestamp.desc())
        .all()
    )

    # Group by unique customer ID
    customers = {}
    for msg in whatsapp_messages:
        c_id = msg.customer_id
        if not c_id: continue
        
        if c_id not in customers:
            customers[c_id] = {
                "id": c_id,
                "name": msg.customer_name or c_id,
                "last_message": msg.text[:50] + "..." if msg.text and len(msg.text) > 50 else (msg.text or ""),
                "last_timestamp": msg.timestamp.strftime("%Y-%m-%d %H:%M"),
                "message_count": 1,
                "ai_enabled": c_id not in AI_DISABLED_USERS
            }
        else:
            customers[c_id]["message_count"] += 1

    return {"customers": list(customers.values())}


@app.get("/api/customer-messages/{customer_name}", tags=["conversations"])
def get_customer_messages(
        customer_name: str,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """Get all messages for a specific WhatsApp customer"""
    business = db.execute(select(Business).where(Business.user_id == current_user.id)).scalar()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    # Get all messages (both customer and bot) for this specific conversation
    messages = (
        db.query(Message)
        .filter(Message.business_id == business.id)
        .filter(Message.platform == 'whatsapp')
        .filter(Message.customer_id == customer_name) # customer_name route param is actually c_id/wa_id
        .order_by(Message.timestamp.asc())
        .all()
    )

    return {
        "customer_name": customer_name,
        "messages": [
            {
                "id": msg.id,
                "text": msg.text,
                "sender": msg.customer_name if not msg.is_bot else "bot",
                "timestamp": msg.timestamp.strftime("%H:%M"),
                "is_bot": msg.is_bot
            }
            for msg in messages
        ]
    }


class ToggleAIRequest(BaseModel):
    customer_id: str
    enable_ai: bool
    message: str | None = None


@app.post("/api/toggle-ai", tags=["chat"])
def api_toggle_ai(
        request: ToggleAIRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    # Fetch business to ensure context
    business = db.execute(
        select(Business).where(Business.user_id == current_user.id)
    ).scalar()

    if not business:
        raise HTTPException(status_code=404, detail="No business found")

    # Update the AI status
    toggle_ai_status(request.customer_id, request.enable_ai)

    # If disabling AI and a message is provided, send it
    if not request.enable_ai and request.message:
        # Send to WhatsApp
        data = get_text_message_input(request.customer_id, request.message)
        response = send_message(data)

        if not response:
            raise HTTPException(status_code=400, detail="Failed to send WhatsApp message. The customer ID might be invalid (names are not allowed, only phone numbers).")

        # Save to database so it appears in the chat history
        # Since we don't have the profile name here, we'll try to find it from previous messages or use ID
        prev_msg = db.query(Message).filter_by(customer_id=request.customer_id).first()
        customer_name = prev_msg.customer_name if prev_msg else request.customer_id
        
        update_conversation_history(
            db=db, 
            business_id=business.id, 
            text=request.message, 
            sender='bot', 
            customer_id=request.customer_id,
            customer_name=customer_name,
            is_bot=True,
            platform='whatsapp'
        )

    return {"status": "success", "ai_enabled": request.enable_ai}


@app.post("/api/chat", tags=["chat"])
async def api_chat_post(
        request: ChatRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    # Fetch business
    business = db.execute(
        select(Business).where(Business.user_id == current_user.id)
    ).scalar()

    if not business:
        raise HTTPException(status_code=404, detail="No business found for this account.")

    user_message = request.message.strip()

    if user_message:
        # Get last 20 messages for context
        recent_messages = (
            db.query(Message)
            .filter(Message.business_id == business.id)
            .order_by(Message.timestamp.desc())
            .limit(20)
            .all()
        )

        conversation_history = [
            {"text": msg.text, "sender": msg.sender, "is_bot": msg.is_bot}
            for msg in reversed(recent_messages)
        ]

        # Save user message
        user_msg = Message(business_id=business.id, text=user_message, sender="user", is_bot=False)
        db.add(user_msg)
        db.commit()

        # AI response
        bot_response = get_ai_response(user_message, db, conversation_history, business_id=business.id)

        # Save bot message
        bot_msg = Message(business_id=business.id, text=bot_response, sender="bot", is_bot=True)
        db.add(bot_msg)
        db.commit()

        return {"response": bot_response}
    return {"response": "I didn't catch that."}


@app.post("/login")
async def login_post(
        request: Request,
        db: Session = Depends(get_db)
):
    form = await request.form()
    username = form.get("username")
    password = form.get("password")

    # Fetch user
    user = db.execute(
        select(User).where(User.username == username)
    ).scalar()

    # Invalid credentials → re-render login page
    if not user or not check_password_hash(user.password_hash, password):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Invalid credentials"},
            status_code=400
        )

    # Create JWT
    access_token = create_access_token({"sub": str(user.id)})

    # Redirect with secure cookie
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,  # JS cannot read it
        secure=True,  # only sent over HTTPS
        samesite="lax",  # safe default
        max_age=3600  # 1 hour
    )

    return response


@app.get("/login")
def login(request: Request):
    return templates.TemplateResponse("login.html", {
        "request": request
    })


@app.get("/signup", name="signup")
def signup_page(request: Request):
    return templates.TemplateResponse(request=request, name="signup.html")


@app.post("/signup")
async def signup_post(request: Request, db: Annotated[Session, Depends(get_db)]):
    form = await request.form()
    username = form.get("username")
    password = form.get("password")
    email = form.get("email")
    business_name = form.get("business_name")

    if not username or not password or not business_name:
        return templates.TemplateResponse(request=request, name="signup.html",
                                          context={"error": "Please fill in all required fields"})

    # Check if username or email already exists
    if db.execute(select(User).where(func.lower(User.username) == func.lower(username))).first():
        return templates.TemplateResponse(request=request, name="signup.html",
                                          context={"error": "Username already exists"})
    if db.execute(select(User).where(func.lower(User.email) == func.lower(email))).first():
        return templates.TemplateResponse(request=request, name="signup.html",
                                          context={"error": "Email already registered"})

    new_user = User(
        username=username,
        email=email,
        password_hash=generate_password_hash(password, method='pbkdf2:sha256', salt_length=8)
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    new_business = Business(name=business_name, user_id=new_user.id)
    db.add(new_business)
    db.commit()

    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/clear-session")
def clear_session():
    pass


@app.get("/products", tags=["Products"], name='products')
def list_products(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        current_user: User = Depends(get_current_user)
):
    business = db.execute(select(Business).where(Business.user_id == current_user.id)).scalar()
    if not business:
        return RedirectResponse(url="/", status_code=303)

    business_products = db.execute(select(Product).where(Product.business_id == business.id)).scalars().all()

    return templates.TemplateResponse(
        "products.html",
        {"request": request, "products": business_products, "business": business}
    )


@app.post("/settings", tags=["Settings"])
async def settings_post(request: Request, db: Annotated[Session, Depends(get_db)],
                        current_user: User = Depends(get_current_user)):
    form = await request.form()
    phone_number_id = form.get("phone_number_id")
    persona = form.get("persona")

    # Clean inputs
    phone_number_id = phone_number_id.strip() if phone_number_id and phone_number_id.strip() else None
    persona = persona.strip() if persona and persona.strip() else None

    business = db.execute(select(Business).where(Business.user_id == current_user.id)).scalar()

    # Check if phone number is already taken by another business
    if phone_number_id:
        existing = db.execute(select(Business).where(
            Business.phone_number_id == phone_number_id,
            Business.id != business.id
        )).scalar()

        if existing:
            return templates.TemplateResponse(
                "settings.html",
                {"request": request, "business": business,
                 "messages": ["This WhatsApp phone number is already registered to another business."],
                 "category": "error"}
            )

    business.phone_number_id = phone_number_id
    business.persona = persona
    db.commit()
    db.refresh(business)

    return templates.TemplateResponse(
        "settings.html",
        {"request": request, "business": business, "messages": ["Settings saved successfully"], "category": "success"}
    )


@app.get("/settings", tags=["Settings"], name="settings")
def settings_page(request: Request, db: Annotated[Session, Depends(get_db)],
                  current_user: User = Depends(get_current_user)):
    business = db.execute(select(Business).where(Business.user_id == current_user.id)).scalar()

    return templates.TemplateResponse(
        "settings.html",
        {"request": request, "business": business})


@app.get("/logout", tags=["Users"])
def logout(request: Request):
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie("access_token")
    return response


@app.get("/logout-page", tags=["Users"], include_in_schema=False)
def logout_page(request: Request):
    return templates.TemplateResponse("logout.html",
                                      {"request": request})


# Request Exception Handler
@app.exception_handler(StarletteHTTPException)
async def validation_exception_handler(request: Request, exception: StarletteHTTPException):
    if exception.status_code == status.HTTP_401_UNAUTHORIZED:
        if not request.url.path.startswith("/api"):
            return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    message = (exception.detail if exception.detail else "An error occurred")

    if request.url.path.startswith("/api"):
        return JSONResponse(status_code=exception.status_code, content={"detail": message})
    return templates.TemplateResponse(request, "error.html",
                                      {"request": request,
                                       "title": exception.status_code,
                                       "message": message
                                       },
                                      status_code=exception.status_code)


# RequestValidationError handler
@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(request: Request, exception: RequestValidationError):
    message = "Invalid data provided"
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY

    if request.url.path.startswith("/api"):
        return JSONResponse(
            status_code=status_code,
            content={"detail": jsonable_encoder(exception.errors())}
        )

    return templates.TemplateResponse(
        "error.html",
        {
            "request": request,
            "status_code": status_code,
            "title": "Validation Error",
            "message": message
        },
        status_code=status_code
    )
