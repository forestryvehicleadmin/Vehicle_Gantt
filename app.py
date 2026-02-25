import streamlit as st
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

# Generate private key
private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

# Get keys in text format
private_pem = private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.OpenSSH,
    encryption_algorithm=serialization.NoEncryption()
).decode('utf-8')

public_key = private_key.public_key().public_bytes(
    encoding=serialization.Encoding.OpenSSH,
    format=serialization.PublicFormat.OpenSSH
).decode('utf-8')

st.title("🔑 Your New SSH Keys")
st.warning("Copy these now! They will disappear if you refresh.")

st.subheader("1. Public Key (Copy this for GitHub)")
st.code(public_key)

st.subheader("2. Private Key (Copy this for Streamlit Secrets)")
st.code(private_pem)
