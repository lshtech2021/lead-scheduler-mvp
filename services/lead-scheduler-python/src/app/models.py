from sqlalchemy import (
    Column, Integer, String, DateTime, Text, JSON, ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func

Base = declarative_base()

class Client(Base):
    __tablename__ = "clients"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    config = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    leads = relationship("Lead", back_populates="client")

class Lead(Base):
    __tablename__ = "leads"
    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey("clients.id"))
    external_id = Column(String)
    phone = Column(String, nullable=False)
    payload = Column(JSON)
    state = Column(String, default="new")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    client = relationship("Client", back_populates="leads")
    messages = relationship("Message", back_populates="lead")
    bookings = relationship("Booking", back_populates="lead")
    proposals = relationship("Proposal", back_populates="lead")

    __table_args__ = (UniqueConstraint("client_id", "external_id", name="uq_client_external"),)

class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True)
    provider_id = Column(String, unique=True, nullable=True)
    direction = Column(String)  # inbound/outbound
    body = Column(Text)
    status = Column(String)
    metadata = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    lead = relationship("Lead", back_populates="messages")

class Call(Base):
    __tablename__ = "calls"
    id = Column(Integer, primary_key=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True)
    provider_id = Column(String, unique=True, nullable=True)
    recording_url = Column(String)
    transcript = Column(Text)
    status = Column(String)
    metadata = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Booking(Base):
    __tablename__ = "bookings"
    id = Column(Integer, primary_key=True)
    lead_id = Column(Integer, ForeignKey("leads.id"))
    provider = Column(String)  # google_calendar, calendly
    provider_booking_id = Column(String)
    start = Column(DateTime(timezone=True))
    end = Column(DateTime(timezone=True))
    status = Column(String)
    reason = Column(Text)
    metadata = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    lead = relationship("Lead", back_populates="bookings")

class Stop(Base):
    __tablename__ = "stops"
    id = Column(Integer, primary_key=True)
    phone = Column(String, unique=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class EventLog(Base):
    __tablename__ = "event_logs"
    id = Column(Integer, primary_key=True)
    lead_id = Column(Integer, nullable=True)
    client_id = Column(Integer, nullable=True)
    event_type = Column(String)
    payload = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class OutboundSend(Base):
    """Idempotency for outbound SMS: (lead_id, message_type, idempotency_key) unique."""
    __tablename__ = "outbound_sends"
    id = Column(Integer, primary_key=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=False)
    message_type = Column(String, nullable=False)
    idempotency_key = Column(String, nullable=False)
    message_id = Column(Integer, ForeignKey("messages.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("lead_id", "message_type", "idempotency_key", name="uq_outbound_idempotency"),)


class Proposal(Base):
    """Proposed slot per lead for confirmation flow."""
    __tablename__ = "proposals"
    id = Column(Integer, primary_key=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=False)
    slot_start = Column(DateTime(timezone=True), nullable=False)
    slot_end = Column(DateTime(timezone=True), nullable=False)
    proposed_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    lead = relationship("Lead", back_populates="proposals")