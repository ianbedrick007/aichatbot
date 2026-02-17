from sqlalchemy import select
from database import engine, get_db
from models import Product, Business, User
from sqlalchemy.orm import Session

def check_products():
    with Session(engine) as db:
        users = db.execute(select(User)).scalars().all()
        print(f"Total Users: {len(users)}")
        for user in users:
            business = db.execute(select(Business).where(Business.user_id == user.id)).scalar()
            if business:
                products = db.execute(select(Product).where(Product.business_id == business.id)).scalars().all()
                print(f"User: {user.username}, Business: {business.name}, Products: {len(products)}")
                for p in products:
                    print(f"  - Product: {p.name}, Price: {p.price}")
            else:
                print(f"User: {user.username} has no business.")

        all_products = db.execute(select(Product)).scalars().all()
        print(f"\nTotal Products across all businesses: {len(all_products)}")

if __name__ == "__main__":
    check_products()
