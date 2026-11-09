# UNCOMMON – Discover the Uncommon

**UNCOMMON** is a modern e-commerce platform designed to offer unique, stylish, and limited-edition fashion products for men and women. The platform focuses on bringing everyday essentials and exclusive collections together in one shopping experience.

Users can explore products, manage their shopping bags, place orders, and discover rare collections.
## 🌐 Live Website

**Visit UNCOMMON:** Explore the Live Website  https://uncommen.in
 ---

## 🚀 Features

### 👤 Customer Module
- User registration and login.
- Browse products for men and women.
- Explore exclusive and limited-edition products.
- View detailed product information.
- Add products to the shopping bag.
- Manage shopping bag items and quantities.
- Secure checkout process.
- Place and track orders.
- View order history.
- Submit feedback.
- Send product reservation requests.

### 🔐 Admin Module
- Secure admin login.
- Dashboard with store statistics.
- Manage customer information.
- Add, update, and delete products.
- Manage product categories.
- Manage orders.
- Update order statuses.
- View customer feedback.
- Manage product reservations.
- Monitor product stock and low-stock products.
- Send email notifications when order statuses change.

### 🛍️ Shopping Experience
- **Insolo Him:** Fashion and essentials for men.
- **Insolo Her:** Fashion and essentials for women.
- **Hundred:** Exclusive and rare limited-edition collections.

---

## 🛠️ Technology Stack

| Technology | Purpose |
|---|---|
| Python | Backend programming |
| Django | Backend framework |
| HTML5 | Page structure |
| CSS3 | Styling and layouts |
| JavaScript | Frontend interactions |
| Bootstrap | Responsive UI components |
| SQLite / PostgreSQL | Database |
| Django ORM | Database management |
| Git & GitHub | Version control |

---

## 📂 Project Structure

```text
UNCOMMON/
│
├── uncommon/
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
│
├── admin_panel/
│   ├── models.py
│   ├── views.py
│   ├── urls.py
│   └── templates/
│
├── customer/
│   ├── models.py
│   ├── views.py
│   ├── urls.py
│   └── templates/
│
├── media/
│
├── static/
│
├── templates/
│
├── manage.py
├── requirements.txt
└── README.md
```

---

## ⚙️ Installation and Setup

Follow these steps to run the project locally.

### 1. Clone the Repository

```bash
git clone https://github.com/Sridhin-KA/UNCOMMON.git
```

### 2. Navigate to the Project Directory

```bash
cd UNCOMMON
```

### 3. Create a Virtual Environment

```bash
python -m venv venv
```

### 4. Activate Virtual Environment

**Linux / macOS**

```bash
source venv/bin/activate
```

**Windows**

```bash
venv\Scripts\activate
```

### 5. Install Dependencies

```bash
pip install -r requirements.txt
```

### 6. Apply Database Migrations

```bash
python manage.py makemigrations
python manage.py migrate
```

### 7. Create a Django Superuser (if required)

```bash
python manage.py createsuperuser
```

### 8. Run the Development Server

```bash
python manage.py runserver
```

Open your browser and visit:

```text
http://127.0.0.1:8000/
```

---

## 🗄️ Database

The project uses Django ORM for database operations.

Main database entities include:

- Admin
- Customer
- Product
- Category
- Bag / Cart
- Order
- Order Item
- Feedback
- Reservation

The database can be configured using SQLite for local development or PostgreSQL for production.

---

## 🔒 Security

- Password hashing using Django authentication utilities.
- Session-based user authentication.
- CSRF protection.
- Admin access restrictions.
- Server-side form validation.
- Environment variables for sensitive configuration.

---

## 🌱 Future Enhancements

- Online payment gateway integration.
- Wishlist functionality.
- Advanced product filtering and search.
- Product ratings and reviews.
- Personalized product recommendations.
- Improved order tracking.
- Enhanced SEO and product discovery.
- Mobile-first shopping experience.

---

## 👨‍💻 Developer

**UNCOMMON – Discover the Uncommon**

Developed using Python and Django.

GitHub: https://github.com/your-username

---

## 📄 License

This project is developed for educational and development purposes. All rights reserved unless otherwise specified.
