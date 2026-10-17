from flask import Flask
import socket

app = Flask(__name__)

@app.route("/")
def home():
    hostname = socket.gethostname()

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>HA Demo Application</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                text-align: center;
                margin-top: 100px;
            }}
            .box {{
                display: inline-block;
                padding: 40px;
                border-radius: 12px;
                box-shadow: 0 4px 15px rgba(0,0,0,0.2);
            }}
            h1 {{
                margin-bottom: 20px;
            }}
        </style>
    </head>
    <body>
        <div class="box">
            <h1>🚀 HA Demo Application</h1>
            <h2>Application is Running</h2>
            <p><b>Container Host:</b> {hostname}</p>
            <p><b>Status:</b> Healthy</p>
        </div>
    </body>
    </html>
    """

@app.route("/health")
def health():
    return {"status": "healthy"}

@app.route("/api/work")
def work():
    total = 0
    for i in range(500000):
        total += i * i

    return {
        "status": "completed",
        "result": total,
        "host": socket.gethostname()
    }

app.run(host="0.0.0.0", port=5000)
