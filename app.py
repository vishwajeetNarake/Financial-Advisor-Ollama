from flask import Flask, render_template, request, redirect, url_for, jsonify, session, flash
from markupsafe import Markup
from database import Database
from ollama import format_prompt, query_ollama
import re
import markdown
import bleach
from datetime import datetime
import os
from functools import wraps

app = Flask(__name__)
app.secret_key = os.urandom(24)  # Generate a random secret key for session
db = Database()

# Helper function to parse Indian currency notations
def parse_currency_value(value_str):
    """
    Parse currency values with Indian notations (cr/crore, lakh, etc.)
    Returns the value in rupees (float)
    """
    if not value_str or isinstance(value_str, (int, float)):
        return value_str
        
    value_str = str(value_str).strip().lower()
    
    # Handle crore notation
    if 'cr' in value_str or 'crore' in value_str:
        value_str = value_str.replace('cr', '').replace('crore', '').strip()
        try:
            return float(value_str) * 10000000  # 1 crore = 10,000,000
        except ValueError:
            return value_str
            
    # Handle lakh notation
    if 'l' in value_str or 'lakh' in value_str:
        value_str = value_str.replace('l', '').replace('lakh', '').strip()
        try:
            return float(value_str) * 100000  # 1 lakh = 100,000
        except ValueError:
            return value_str
            
    # Return as is if no special notation found
    try:
        return float(value_str)
    except ValueError:
        return value_str

# Helper function to format currency values for display
def format_currency_value(value, include_rupee_symbol=True):
    """
    Format numerical values into Indian currency format (crore, lakh)
    """
    if value is None or value == '':
        return ''
        
    try:
        value = float(value)
    except (ValueError, TypeError):
        return str(value)
        
    # Format as crore for values >= 10,000,000
    if value >= 10000000:
        formatted = f"{value/10000000:.2f} crore"
    # Format as lakh for values >= 100,000
    elif value >= 100000:
        formatted = f"{value/100000:.2f} lakh"
    # Format as regular number for smaller values
    else:
        formatted = f"{value:,.2f}"
        
    if include_rupee_symbol:
        return f"₹{formatted}"
    return formatted

# Add this context processor for templates
@app.context_processor
def utility_processor():
    """Add utility functions to template context"""
    def now():
        return datetime.now()
    return dict(now=now, format_currency=format_currency_value)

# User authentication decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def format_ollama_response(raw_response):
    """Format the Ollama response for better readability and modern display"""
    # Step 1: Handle bold text formatting
    formatted = re.sub(r"(\*\*.*?\*\*)", r"\1\n", raw_response)
    
    # Step 2: Add paragraph breaks for numbered items
    formatted = re.sub(r'(\d+\.\s)', r'\n\1', formatted)
    
    # Step 3: Convert Markdown to HTML for rich formatting
    html_content = markdown.markdown(formatted)
    
    # Step 4: Sanitize HTML to prevent XSS
    allowed_tags = ['p', 'h1', 'h2', 'h3', 'h4', 'b', 'i', 'strong', 'em', 'ul', 'ol', 'li', 'br']
    allowed_attrs = {'*': ['class']}
    clean_html = bleach.clean(html_content, tags=allowed_tags, attributes=allowed_attrs)
    
    # Step 5: Add custom styling classes for better display
    # Add classes to headings and paragraphs
    clean_html = clean_html.replace('<h3>', '<h3 class="advice-heading">')
    clean_html = clean_html.replace('<p>', '<p class="advice-paragraph">')
    
    # Step 6: Wrap the entire content in a div for styling
    final_html = f'<div class="advice-content">{clean_html}</div>'
    
    return Markup(final_html)

@app.route('/', methods=['GET'])
def index():
    # Redirect to login page as the first page
    return redirect(url_for('login'))

@app.route('/loan_form', methods=['GET'])
def loan_form():
    # This route now shows the loan application form (the old index page)
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = db.login_user(username, password)
        if user:
            session['user_id'] = str(user['_id'])
            session['username'] = user['username']
            return redirect(url_for('dashboard'))
        else:
            return render_template('login.html', error='Invalid username or password')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        # Validate passwords match
        if password != confirm_password:
            return render_template('register.html', error='Passwords do not match')
        
        # Register user
        user_id = db.register_user(username, password, email)
        if user_id:
            session['user_id'] = str(user_id)
            session['username'] = username
            return redirect(url_for('dashboard'))
        else:
            return render_template('register.html', error='Username already exists')
    
    return render_template('register.html')

@app.route('/dashboard')
@login_required
def dashboard():
    user_id = session.get('user_id')
    applications = db.get_all_applications(user_id)
    return render_template('dashboard.html', applications=applications, username=session.get('username'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))   

@app.route('/submit', methods=['POST'])
def submit():
    # Get form data and store in database
    form_data = request.form.to_dict()
    
    # Process currency values with Indian notation
    currency_fields = ['loanAmount', 'annualIncome', 'existingDebt', 'monthlyExpenses', 'savings']
    for field in currency_fields:
        if field in form_data and form_data[field]:
            # Parse and standardize the currency values
            form_data[field] = parse_currency_value(form_data[field])
            
    # Add timestamp
    form_data['created_at'] = datetime.utcnow()
    
    # Add user_id if logged in
    if 'user_id' in session:
        user_id = session.get('user_id')
        application_id = db.store_application(form_data, user_id)
    else:
        application_id = db.store_application(form_data)

    # Get data back from MongoDB
    user_data = db.get_application(application_id)

    # Generate prompt and call Ollama
    prompt = format_prompt(user_data)
    ollama_output = query_ollama(prompt)

    # Format Ollama output for better readability
    formatted_output = format_ollama_response(ollama_output)
    
    # Get current timestamp for display
    timestamp = datetime.now().strftime("%B %d, %Y at %I:%M %p")

    # Make sure we're passing all required variables to the template
    return render_template(
        "success.html", 
        application_id=application_id,
        advice=formatted_output,
        timestamp=timestamp,
        user_data=user_data,
        format_currency=format_currency_value
    )

@app.route('/api/advice/<application_id>', methods=['GET'])
def get_advice_api(application_id):
    """API endpoint to get advice for a specific application"""
    user_data = db.get_application(application_id)
    if not user_data:
        return jsonify({"error": "Application not found"}), 404
    
    prompt = format_prompt(user_data)
    ollama_output = query_ollama(prompt)
    formatted_output = format_ollama_response(ollama_output)
    
    return jsonify({
        "application_id": application_id,
        "advice_html": str(formatted_output),
        "raw_advice": ollama_output,
        "timestamp": datetime.now().isoformat()
    })

@app.route('/applications', methods=['GET'])
@login_required
def view_applications():
    """View all applications - admin feature"""
    applications = db.get_all_applications()
    return render_template('applications.html', applications=applications)

@app.route('/application/<application_id>', methods=['GET'])
def view_application(application_id):
    """View a specific application with advice"""
    user_data = db.get_application(application_id)
    if not user_data:
        return redirect(url_for('index'))
    
    # Check if user is authorized to view this application
    if 'user_id' in session and 'user_id' in user_data:
        if session['user_id'] != str(user_data['user_id']):
            return redirect(url_for('dashboard'))
        
    # Generate or retrieve advice
    prompt = format_prompt(user_data)
    ollama_output = query_ollama(prompt)
    formatted_output = format_ollama_response(ollama_output)
    
    # Get current timestamp for display
    timestamp = datetime.now().strftime("%B %d, %Y at %I:%M %p")
    
    return render_template(
        "application_detail.html", 
        application_id=application_id,
        advice=formatted_output,
        user_data=user_data,
        timestamp=timestamp,
        format_currency=format_currency_value
    )

# New routes for chatbot functionality
@app.route('/chat/<application_id>', methods=['POST'])
def chat_with_advisor(application_id):
    """API endpoint to chat with the financial advisor about a specific application"""
    user_data = db.get_application(application_id)
    if not user_data:
        return jsonify({"error": "Application not found"}), 404
    
    # Get the user's question
    question = request.json.get('question', '')
    if not question:
        return jsonify({"error": "No question provided"}), 400
    
    # Format currency values for context
    loan_amount = format_currency_value(user_data.get('loanAmount', ''))
    annual_income = format_currency_value(user_data.get('annualIncome', ''))
    
    # Create a chat prompt that includes context from the user's application
    chat_prompt = f"""
    Context: This user has submitted a loan application with the following details:
    - Name: {user_data.get('name')}
    - Loan Amount: {loan_amount}
    - Loan Purpose: {user_data.get('loanPurpose')}
    - Credit Score: {user_data.get('creditScore')}
    - Annual Income: {annual_income}
    
    User asks: {question}
    
    Provide a helpful, accurate, and personalized response addressing their question about finances or loans. 
    Keep the response concise yet informative.
    """
    
    # Query Ollama with the chat prompt
    response = query_ollama(chat_prompt)
    
    # Format the response
    formatted_response = format_ollama_response(response)
    
    # Store the chat in the database
    chat_data = {
        "application_id": application_id,
        "question": question,
        "response": response,
        "formatted_response": str(formatted_response),  # Store formatted response too
        "timestamp": datetime.utcnow()
    }
    db.store_chat(chat_data)
    
    return jsonify({
        "response_html": str(formatted_response),
        "raw_response": response,
        "timestamp": datetime.now().isoformat()
    })

@app.route('/admin_chat', methods=['POST'])
def admin_chat():
    """API endpoint for the admin chat in applications.html"""
    question = request.json.get('question', '')
    if not question:
        return jsonify({"error": "No question provided"}), 400

    chat_prompt = f"""
    Context: You are a financial advisor providing general advice to an administrator of a loan application system.
    
    User asks: {question}
    
    Provide a helpful, accurate, and informative response addressing their question about finances, loans, or financial best practices.
    Keep the response concise yet informative. Include specific examples or recommendations when appropriate.
    """
    
    response = query_ollama(chat_prompt)
    formatted_response = format_ollama_response(response)
    
    # Optionally, store the admin chat in the database if needed:
    chat_data = {
        "admin_id": session.get('user_id'),
        "question": question,
        "response": response,
        "formatted_response": str(formatted_response),
        "timestamp": datetime.utcnow()
    }
    # Uncomment the following line if you have implemented the storage method
    # db.store_admin_chat(chat_data)
    
    return jsonify({
        "response_html": str(formatted_response),
        "raw_response": response,
        "timestamp": datetime.now().isoformat()
    })

@app.route('/application/<application_id>/chat_history', methods=['GET'])
def get_chat_history(application_id):
    """Get the chat history for a specific application"""
    # Check if user is authorized to view this chat history
    user_data = db.get_application(application_id)
    
    # Only check authorization if user is logged in and application has user_id
    if 'user_id' in session and user_data and 'user_id' in user_data:
        if session['user_id'] != str(user_data['user_id']):
            return jsonify({"error": "Unauthorized"}), 403
    
    chat_history = db.get_chat_history(application_id)
    
    # Format each response in the chat history
    for chat in chat_history:
        if 'formatted_response' not in chat:
            chat['formatted_response'] = str(format_ollama_response(chat['response']))
    
    return jsonify({"chat_history": chat_history})

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('500.html'), 500

if __name__ == '__main__':
    app.run(debug=True)