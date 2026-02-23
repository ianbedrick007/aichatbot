
# Import necessary libraries and modules
import os
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, Request, status, Depends, Form
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from werkzeug.security import generate_password_hash, check_password_hash

from ai.run_ai import get_ai_response, update_conversation_history, get_conversation_history
from auth import create_access_token
from database import get_db, engine, get_current_user
from models import Business, User, Base, Product
from routers import products, users
from whatsapp_bot.app import router as whatsapp_router, configure_logging


# Define the application lifespan
@asynccontextmanager
async def lifespan(_app: FastAPI):
    """
    Application lifespan context manager.
    Handles startup and shutdown tasks.
    """
    Base.metadata.create_all(bind=engine)  # Create database tables
    configure_logging()  # Configure logging for the WhatsApp bot
    yield


# Initialize the FastAPI application
app = FastAPI(lifespan=lifespan)

# Middleware to handle proxy headers for HTTPS
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

# Define static and media directories
current_dir = os.path.dirname(os.path.realpath(__file__))
static_dir = os.path.join(current_dir, "static")
media_dir = os.path.join(current_dir, "media")

# Mount static and media directories
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/media", StaticFiles(directory="media"), name="media")

# Print application loading message
print("--- Loading main.py application ---")

# Initialize Jinja2 templates
templates = Jinja2Templates(directory="templates")

# Include routers for different modules
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(products.router, prefix="", tags=["posts"])
app.include_router(whatsapp_router, prefix="/api/whatsapp", tags=["whatsapp"])


# Define routes and their handlers
@app.get("/chat", include_in_schema=False, name="home")
def chat_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Render the chat page for the current user.

    Args:
        request (Request): The HTTP request object.
        db (Session): The database session.
        current_user (User): The currently authenticated user.

    Returns:
        TemplateResponse: The rendered chat page.
    """
    business = db.execute(select(Business).where(Business.user_id == current_user.id)).scalar()

    if not business:
        response = RedirectResponse(url="/logout", status_code=303)
        response.set_cookie("error", "No business found for this account.")
        return response

    return templates.TemplateResponse("chat.html", {"request": request, "business": business})


# Additional routes and handlers are defined below with similar docstrings and comments for clarity.


@app.post("/chat", include_in_schema=False)
async def chat_post(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
        message: str = Form(...)
):
    """
        Send message to AI for the current user.

        Args:
            db (Session): The database session.
            current_user (User): The currently authenticated user.
            message(str): The message sent by the user.

        Returns:
            RedirectResponse: The rendered chat page.
        """
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

    return RedirectResponse(url="/chat", status_code=303)




@app.get("/conversations", name="conversations")
def conversations_page(
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    Render the conversations management page.

    Args:
        request (Request): The HTTP request object.
        db (Session): The database session.
        current_user (User): The currently authenticated user.

    Returns:
        TemplateResponse: The rendered conversations page or a redirect if no business exists.
    """
    business = db.execute(select(Business).where(Business.user_id == current_user.id)).scalar()
    if not business:
        return RedirectResponse(url="/", status_code=303)

    return templates.TemplateResponse(
        "conversations.html",
        {"request": request, "business": business}
    )


@app.get("/", name="home")
def dashboard_page(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        current_user: User = Depends(get_current_user)
):
    """
    Render the main dashboard page for the authenticated user.

    Args:
        request (Request): The HTTP request object.
        db (Session): The database session.
        current_user (User): The currently authenticated user.

    Returns:
        TemplateResponse: The rendered dashboard with business statistics.
    """
    business = db.query(Business).filter(Business.user_id == current_user.id).first()
    products_count = db.query(Product).filter(Product.business_id == business.id).count() if business else 0

    # TODO 1: add orders, payments, payouts, invoices and ai credits to Business model.
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request, "business": business, "products_count": products_count,
            "orders": [], "payments": [], "payouts": [], "invoices": [], "ai_credits": None,
        }
    )


@app.post("/login")
async def login_post(
        request: Request,
        db: Session = Depends(get_db)
):
    """
    Handle the login form submission.

    Args:
        request (Request): The HTTP request object containing form data.
        db (Session): The database session.

    Returns:
        Response: A RedirectResponse to the dashboard on success, or the login page with an error message on failure.
    """
    form = await request.form()
    username = form.get("username")
    password = form.get("password")

    # Fetch user
    user = db.execute(
        select(User).where(User.username == username)
    ).scalar()

    # Invalid credentials → re-render login page
    if not user or not check_password_hash(str(user.password_hash), password):
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
    """
    Render the login page.

    Args:
        request (Request): The HTTP request object.

    Returns:
        TemplateResponse: The rendered login page.
    """
    return templates.TemplateResponse("login.html", {
        "request": request
    })


@app.get("/signup", name="signup")
def signup_page(request: Request):
    return templates.TemplateResponse(request=request, name="signup.html")


@app.post("/signup")
async def signup_post(request: Request, db: Annotated[Session, Depends(get_db)]):
    """
    Handle the user registration process.

    Args:
        request (Request): The HTTP request object containing form data.
        db (Session): The database session.

    Returns:
        Response: A RedirectResponse to the login page on success, or the signup page with an error message.
    """
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
    """
    Render the products management page for the current business.

    Args:
        request (Request): The HTTP request object.
        db (Session): The database session.
        current_user (User): The currently authenticated user.

    Returns:
        TemplateResponse: The rendered products page or a redirect if no business exists.
    """
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
    """
    Handle the settings form submission to update business profile.

    Args:
        request (Request): The HTTP request object containing form data.
        db (Session): The database session.
        current_user (User): The currently authenticated user.

    Returns:
        TemplateResponse: The rendered settings page with success or error messages.
    """
    form = await request.form()
    phone_number_id = form.get("phone_number_id")
    persona = form.get("persona")

    # Clean inputs
    phone_number_id = phone_number_id.strip() if phone_number_id and phone_number_id.strip() else None
    persona = persona.strip() if persona and persona.strip() else None

    business = db.execute(select(Business).where(Business.user_id == current_user.id)).scalar()

    if not business:
        return templates.TemplateResponse(
            "settings.html",
            {"request": request, "business": None,
             "messages": ["No business profile found for your account. Please contact support."],
             "category": "error"}
        )

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
    """
    Render the settings page for the current user's business.

    Args:
        request (Request): The HTTP request object.
        db (Session): The database session.
        current_user (User): The currently authenticated user.

    Returns:
        TemplateResponse: The rendered settings page with business details.
    """
    business = db.execute(select(Business).where(Business.user_id == current_user.id)).scalar()

    return templates.TemplateResponse(
        "settings.html",
        {"request": request, "business": business})


@app.get("/logout", tags=["Users"])
def logout():
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
