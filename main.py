from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import stripe
import resend
import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
resend.api_key = os.getenv("RESEND_API_KEY")
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("FRONTEND_URL", "http://localhost:8000")],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/api/create-checkout-session")
async def create_checkout_session():
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price": os.getenv("STRIPE_PRICE_ID"),
                "quantity": 1,
            }],
            mode="payment",
            success_url=os.getenv("FRONTEND_URL") + "/success.html",
            cancel_url=os.getenv("FRONTEND_URL") + "/index.html",
            billing_address_collection="required",
        )
        return JSONResponse({"url": session.url})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, os.getenv("STRIPE_WEBHOOK_SECRET")
        )
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        customer_email = session["customer_details"]["email"]
        customer_name  = session["customer_details"]["name"]
        amount         = session["amount_total"] / 100
        payment_id     = session["payment_intent"]

        print("=== INSERTING ===")
        print(f"Email: {customer_email}, Name: {customer_name}, Amount: {amount}")

        try:
            result = supabase.table("purchases").insert({
                "email":      customer_email,
                "name":       customer_name,
                "amount":     amount,
                "payment_id": payment_id,
                "status":     "completed",
            }).execute()
            print("=== SUPABASE OK ===", result)
        except Exception as e:
            print("=== SUPABASE ERROR ===", str(e))

        try:
            resend.Emails.send({
                "from":    "AutoHR Studio <onboarding@resend.dev>",
                "to":      customer_email,
                "subject": "Your n8n HR Automation Template is here!",
                "html":    f"""
                    <div style="font-family:Inter,sans-serif;max-width:520px;margin:0 auto;padding:40px 20px;color:#1a1a1a">
                      <h1 style="font-size:24px;margin-bottom:8px">Thank you, {customer_name}!</h1>
                      <p style="color:#666;line-height:1.6">Your purchase was successful. Here is your download link:</p>
                      <a href="{os.getenv('DOWNLOAD_URL')}"
                         style="display:inline-block;margin:24px 0;background:#1a1a1a;color:#fff;padding:14px 32px;text-decoration:none;font-size:13px">
                        Download Template
                      </a>
                      <p style="color:#999;font-size:12px">Payment ID: {payment_id}</p>
                    </div>
                """,
            })
            print("=== EMAIL SENT ===")
        except Exception as e:
            print("=== EMAIL ERROR ===", str(e))

    return JSONResponse({"status": "ok"})


@app.get("/")
def root():
    return {"status": "AutoHR Studio API running"}