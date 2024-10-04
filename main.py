import os
from llama_index.core import GPTVectorStoreIndex, Document
from PyPDF2 import PdfReader
import openai
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from dotenv import load_dotenv
import re

app = FastAPI()

load_dotenv()

# Set your OpenAI API key
openai.api_key = os.getenv('OPENAI_API_KEY')

# Load PDFs from a folder
def load_pdfs_from_folder(folder):
    pdf_texts = []
    for filename in os.listdir(folder):
        if filename.endswith('.pdf'):
            reader = PdfReader(os.path.join(folder, filename))
            for page in reader.pages:
                pdf_texts.append(page.extract_text())
    return pdf_texts

# Function to build an index from loaded texts
def build_index_from_texts(texts):
    return GPTVectorStoreIndex.from_documents([Document(text=text) for text in texts])

# Initialize the query engine
pdf_folder_path = 'pdf_files'  # Ensure this points to your correct folder
pdf_texts = load_pdfs_from_folder(pdf_folder_path)
index = build_index_from_texts(pdf_texts)
query_engine = index.as_query_engine()

# Compliance calculation functions
def calculate_csr(net_profit):
    return net_profit * 0.02

def calculate_tax(company_type, profit):
    tax_rate = 0.25 if company_type == 'pvt_ltd' else 0.30
    return profit * tax_rate

def calculate_gst(turnover):
    return turnover * 0.18

def calculate_pf_esi(employee_salary, num_employees):
    pf_amount = employee_salary * 0.12 * num_employees
    esi_amount = employee_salary * 0.0075 * num_employees
    return pf_amount, esi_amount

def calculate_next_billing_date(last_billing_date, frequency):
    if frequency == "monthly":
        return last_billing_date + timedelta(days=30)
    elif frequency == "quarterly":
        return last_billing_date + timedelta(days=90)
    elif frequency == "annual":
        return last_billing_date + timedelta(days=365)
    return last_billing_date

# Define the ComplianceRequest model
class ComplianceRequest(BaseModel):
    question: str

# Store the last question and answer in memory (for a single user)
last_question = None
last_answer = None

@app.get("/", response_class=HTMLResponse)
async def read_root():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Compliance Chatbot</title>
        <style>
            body {
                font-family: Arial, sans-serif;
            }
            .chatbox {
                width: 60%;
                margin: 0 auto;
                background-color: #f7f7f7;
                padding: 20px;
                border-radius: 10px;
                box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);
            }
            .message {
                padding: 10px;
                margin-bottom: 10px;
                border-radius: 5px;
            }
            .question {
                text-align: left;
                background-color: #e0e0e0;
                margin-left: 0;
                margin-right: auto;
            }
            .answer {
                text-align: left;
                background-color: #d1ffd6;
                margin-left: auto;
                margin-right: 0;
            }
            .input-box {
                display: flex;
                margin-top: 20px;
            }
            input[type="text"] {
                flex-grow: 1;
                padding: 10px;
                border-radius: 5px;
                border: 1px solid #ccc;
            }
            button {
                padding: 10px;
                border-radius: 5px;
                border: none;
                background-color: #4CAF50;
                color: white;
                margin-left: 10px;
                cursor: pointer;
            }
        </style>
        <script>
            async function askQuestion() {
                const question = document.getElementById('question').value;
                
                // Create question element
                const questionDiv = document.createElement('div');
                questionDiv.className = 'message question';
                questionDiv.innerHTML = question;
                
                // Append the question to the chatbox
                document.getElementById('chatbox').appendChild(questionDiv);

                // Clear the input box
                document.getElementById('question').value = '';

                const response = await fetch('/ask', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ question }),
                });

                if (response.ok) {
                    const data = await response.json();
                    
                    // Create answer element
                    const answerDiv = document.createElement('div');
                    answerDiv.className = 'message answer';
                    answerDiv.innerHTML = data.answer;
                    
                    // Append the answer to the chatbox
                    document.getElementById('chatbox').appendChild(answerDiv);
                } else {
                    document.getElementById('response').innerHTML = "Error occurred: " + response.statusText;
                }
            }
        </script>
    </head>
    <body>
        <h1>Compliance Chatbot</h1>
        <div class="chatbox" id="chatbox"></div>
        <div class="input-box">
            <input type="text" id="question" placeholder="Ask your compliance question" />
            <button onclick="askQuestion()">Ask</button>
        </div>
    </body>
    </html>
    """

@app.post("/ask")
async def ask_compliance(request: ComplianceRequest):
    global last_question, last_answer  # Use global variables to store the last question and answer

    question = request.question.lower()

    # Handle follow-up questions
    if "in detail" in question or "can you explain more" in question:
        if last_answer is not None:
            return {"answer": generate_detailed_response(last_answer)}
        else:
            return {"answer": "I'm not sure what you're referring to. Could you please specify the question?"}

    # Process the main question and store the last question and answer
    try:
        response = query_engine.query(question)
        last_question = question
        last_answer = str(response)
        return {"answer": last_answer}
    except Exception as e:
        return {"answer": "Sorry, I couldn't process your question."}

def generate_detailed_response(previous_answer):
    # Here you can enhance the response based on the previous answer
    return f"Here's more detail on that: {previous_answer}. You can ask more specific questions if needed!"

# Helper functions to extract details from the question
def extract_value_from_question(question):
    match = re.search(r'\d+', question)
    return float(match.group()) if match else None

def extract_company_type_and_profit(question):
    company_types = ["pvt_ltd", "public", "partnership"]
    for company in company_types:
        if company in question:
            profit = extract_value_from_question(question)
            return company, profit
    return None, None

def extract_salary_and_employees(question):
    salary = extract_value_from_question(question)
    num_employees = extract_value_from_question(question)
    return salary, num_employees

def extract_billing_details(question):
    date_match = re.search(r'(\d{4}-\d{2}-\d{2})', question)
    frequency = "monthly"
    if "quarterly" in question:
        frequency = "quarterly"
    elif "annual" in question or "yearly" in question:
        frequency = "annual"
    
    last_billing_date = datetime.strptime(date_match.group(1), '%Y-%m-%d') if date_match else None
    return last_billing_date, frequency

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8000, log_level="info")
