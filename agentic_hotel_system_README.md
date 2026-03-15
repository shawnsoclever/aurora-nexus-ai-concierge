
# Agentic Hotel Management System

## Overview

The Agentic Hotel Management System is a multi-agent AI platform designed to automate hotel operations including reservations, room assignment, billing, service upselling, and complaint handling.

The system integrates:

- Multi-agent orchestration
- Google Sheets as the operational database
- MCP tools for database access
- FastAPI backend
- Laravel + Bootstrap frontend

The goal is to simulate a real-world AI hotel concierge and operations management platform.

---

# System Architecture

Customer
   │
Laravel + Bootstrap Frontend
   │
FastAPI Backend
   │
Agent Orchestrator
   │
AI Agents
   │
MCP Tool Server
   │
Google Sheets Database

---

# Project Directory Structure

The project must follow this structure:

/agents        - Agent logic and prompts  
/tools         - MCP tool servers  
/app           - Frontend application (Laravel + Bootstrap)  
requirements.txt  
README.md  

---

# Frontend (Laravel + Bootstrap)

The frontend provides the interface for hotel customers.

Features:

- Conversational chat interface
- Room reservation interaction
- Booking confirmation display
- Service request interface
- Complaint submission

Technology stack:

- Laravel
- Bootstrap
- Blade Templates
- Axios / Fetch API

The frontend communicates with FastAPI through REST APIs.

Example request:

POST /api/chat

{
  "message": "I want to book a room tomorrow"
}

---

# Backend (FastAPI)

FastAPI manages AI orchestration.

Responsibilities:

- Receive frontend requests
- Maintain conversation state
- Execute multi-agent workflows
- Call MCP tools
- Return responses

---

# API Endpoints

POST /api/chat  
Handles conversation requests.

POST /api/booking  
Creates a reservation.

GET /api/rooms/available  
Returns available rooms.

POST /api/payment  
Processes mock payment transactions.

POST /api/complaints  
Registers a guest complaint.

---

# Agents

Conversation Agent
      │
Guest Profiling Agent
      │
Workflow Orchestrator
      │
 ├ Reservation Agent
 ├ Room Assignment Agent
 ├ Billing Agent
 ├ Upsell Agent
 └ Support Agent

---

# Agent Responsibilities

## Conversation Agent
Handles conversation with the customer.
- Greets guest
- Collects information
- Maintains context

No database access.

## Guest Profiling Agent
Extracts structured data from conversation.

Fields extracted:
- guest_type
- stay_purpose
- group_size
- preferences

Access:
Guests sheet (write)

## Workflow Orchestrator
Coordinates agent workflow.
- Routes tasks
- Maintains state
- Enforces guardrails

No direct database access.

## Reservation Agent
Handles reservation logic.

Access:
Rooms (read)  
Bookings (write)

## Room Assignment Agent
Assigns suitable rooms.

Access:
Rooms (read/write)

## Billing Agent
Processes payments (mock).

Access:
Payments (write)  
Bookings (read)

## Upsell Agent
Suggests additional services.

Access:
Services (read)

## Support Agent
Handles customer complaints.

Access:
Complaints (write)  
Bookings (read)  
Guests (read)

---

# Google Sheets Database

Sheets used:

Rooms  
Guests  
Bookings  
Payments  
Services  
Complaints  

---

# Data Relationships

Guests
  │
Bookings
  │
Rooms
  │
Payments

Guests
  │
Complaints

---

# MCP Tool Layer

Agents interact with Google Sheets through MCP tools.

Example tools:

add_guest()  
find_available_room()  
create_booking()  
update_room_status()  
log_payment()  
read_services()  
log_complaint()  

Agents never access sheets directly.

---

# Security Guardrails

- Agents cannot modify primary keys
- Sheet access restricted by role
- Double booking prevention
- Prompt injection protection
- Audit logging

---

# Dependencies

Install dependencies:

pip install -r requirements.txt

Key packages include:

fastapi  
uvicorn  
pydantic  
python-dotenv  
gspread  
google-auth  
requests  
httpx  
langchain  
pandas  
numpy  
loguru  
tenacity  
orjson  

---

# Credentials

The Google service account credentials file:

final-nexus-1029-01234e2a6a89.json

This file enables MCP tools to access Google Sheets.

---

# Project Goal

Demonstrate a production-style agentic AI architecture capable of managing hotel operations autonomously with structured workflows, secure data handling, and conversational interfaces.
