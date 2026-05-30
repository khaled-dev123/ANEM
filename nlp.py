import ollama 
import pdfplumber
import json


with pdfplumber.open("cv_test.pdf") as pdf:
    text = "\n".join(page.extract_text() for page in pdf.pages)

responese = ollama.chat(
    model = "mistral",
    messages = [{
        "role" : "user",
        "content" : f"Extract this resume into JSON ( name, email, phone, skills, experience, education). Return JSON only, no explanation:\n\n{text}"
    }]
)

data = json.loads(responese['message']['content'])
print(data)