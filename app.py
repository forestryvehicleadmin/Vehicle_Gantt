import streamlit as st
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

st.title("🔑 Your New SSH Keys")

# This creates the digital 'DNA' of your key
key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

# Format the Private Key (The 'Key')
private_pem = key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.OpenSSH,
    encryption_algorithm=serialization.NoEncryption()
).decode('utf-8')

# Format the Public Key (The 'Lock')
public_key = key.public_key().public_bytes(
    encoding=serialization.Encoding.OpenSSH,
    format=serialization.PublicFormat.OpenSSH
).decode('utf-8')

st.subheader("1. Public Key (For GitHub)")
st.code(public_key)

st.subheader("2. Private Key (For Streamlit Secrets)")
st.code(private_pem)
