"""
Stripe Payment Integration for ETH Trading Bot
Handles checkout sessions, webhooks, and subscription upgrades
"""

import os
import stripe
from typing import Optional, Dict

# Initialize Stripe with secret key
stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")

# Price IDs for subscription tiers
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID", "")  # Premium tier price

# Product configuration
PRODUCTS = {
    "premium": {
        "name": "Premium Subscription",
        "price_id": STRIPE_PRICE_ID,
        "price": 2900,  # $29.00 in cents
        "currency": "usd"
    }
}


def create_checkout_session(
    user_id: int,
    user_email: str,
    tier: str = "premium",
    success_url: str = None,
    cancel_url: str = None
) -> Optional[Dict]:
    """
    Create a Stripe Checkout session for subscription upgrade
    
    Args:
        user_id: User ID to associate with the subscription
        user_email: User's email for Stripe
        tier: Subscription tier to purchase
        success_url: URL to redirect on success
        cancel_url: URL to redirect on cancel
        
    Returns:
        Dict with checkout session URL and ID, or None on error
    """
    if not stripe.api_key:
        print("⚠️ Stripe API key not configured")
        return None
    
    product = PRODUCTS.get(tier)
    if not product:
        print(f"⚠️ Unknown tier: {tier}")
        return None
    
    base_url = os.getenv("DASHBOARD_URL", "http://localhost:3000")
    success_url = success_url or f"{base_url}/subscription?success=true"
    cancel_url = cancel_url or f"{base_url}/subscription?canceled=true"
    
    try:
        # Create checkout session
        if product["price_id"]:
            # Use existing price ID (subscription mode)
            session = stripe.checkout.Session.create(
                payment_method_types=["card"],
                line_items=[{
                    "price": product["price_id"],
                    "quantity": 1,
                }],
                mode="subscription",
                success_url=success_url,
                cancel_url=cancel_url,
                customer_email=user_email,
                client_reference_id=str(user_id),
                metadata={
                    "user_id": str(user_id),
                    "tier": tier
                }
            )
        else:
            # Create one-time payment (fallback for testing)
            session = stripe.checkout.Session.create(
                payment_method_types=["card"],
                line_items=[{
                    "price_data": {
                        "currency": product["currency"],
                        "product_data": {
                            "name": product["name"],
                        },
                        "unit_amount": product["price"],
                    },
                    "quantity": 1,
                }],
                mode="payment",
                success_url=success_url,
                cancel_url=cancel_url,
                customer_email=user_email,
                client_reference_id=str(user_id),
                metadata={
                    "user_id": str(user_id),
                    "tier": tier
                }
            )
        
        return {
            "checkout_url": session.url,
            "session_id": session.id
        }
        
    except stripe.error.StripeError as e:
        print(f"❌ Stripe error: {e}")
        return None
    except Exception as e:
        print(f"❌ Error creating checkout: {e}")
        return None


def verify_webhook_signature(payload: bytes, signature: str) -> Optional[Dict]:
    """
    Verify Stripe webhook signature and parse event
    
    Args:
        payload: Raw request body
        signature: Stripe-Signature header value
        
    Returns:
        Parsed Stripe event or None if invalid
    """
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    
    if not webhook_secret:
        print("⚠️ Stripe webhook secret not configured")
        return None
    
    try:
        event = stripe.Webhook.construct_event(
            payload, signature, webhook_secret
        )
        return event
    except stripe.error.SignatureVerificationError as e:
        print(f"❌ Webhook signature verification failed: {e}")
        return None
    except Exception as e:
        print(f"❌ Webhook error: {e}")
        return None


def handle_successful_payment(user_id: int, tier: str) -> bool:
    """
    Upgrade user subscription after successful payment
    
    Args:
        user_id: User ID to upgrade
        tier: New subscription tier
        
    Returns:
        True if upgrade successful
    """
    from subscription_manager import SubscriptionManager
    
    try:
        sub_mgr = SubscriptionManager()
        success = sub_mgr.upgrade_user(user_id, tier)
        
        if success:
            print(f"✅ User {user_id} upgraded to {tier}")
        else:
            print(f"❌ Failed to upgrade user {user_id}")
        
        return success
    except Exception as e:
        print(f"❌ Error upgrading user: {e}")
        return False


def get_subscription_status(customer_id: str) -> Optional[Dict]:
    """
    Get subscription status from Stripe
    
    Args:
        customer_id: Stripe customer ID
        
    Returns:
        Subscription status dict or None
    """
    if not stripe.api_key:
        return None
    
    try:
        subscriptions = stripe.Subscription.list(
            customer=customer_id,
            status="active",
            limit=1
        )
        
        if subscriptions.data:
            sub = subscriptions.data[0]
            return {
                "status": sub.status,
                "current_period_end": sub.current_period_end,
                "cancel_at_period_end": sub.cancel_at_period_end
            }
        
        return None
    except stripe.error.StripeError as e:
        print(f"❌ Stripe error: {e}")
        return None


if __name__ == "__main__":
    # Test Stripe integration
    print("Stripe Integration Test")
    print(f"API Key configured: {'Yes' if stripe.api_key else 'No'}")
    print(f"Price ID configured: {'Yes' if STRIPE_PRICE_ID else 'No'}")
