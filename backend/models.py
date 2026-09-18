"""
Modèles SQLAlchemy — mappés sur schema.sql (source de vérité fournie par l'utilisateur).
Les tables sont créées par exécution directe de schema.sql (voir database.py),
pas par Base.metadata.create_all — ces classes servent uniquement à l'ORM
pour lire/écrire dans des tables déjà existantes.
"""
from __future__ import annotations

from sqlalchemy import (
    BigInteger, Boolean, Column, Date, DateTime, ForeignKey, Integer,
    Numeric, SmallInteger, String, Text, UniqueConstraint, func
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("document_type", "source_file"),)

    document_id = Column(BigInteger, primary_key=True)
    document_type = Column(String(10), nullable=False)  # 'HEALTH' | 'DGM' | 'DGD'
    source_file = Column(Text, nullable=False)
    extracted_at = Column(DateTime(timezone=True))
    ship_name = Column(Text)
    imo_number = Column(String(20))
    voyage_no = Column(Text)
    loaded_at = Column(DateTime(timezone=True), server_default=func.now())
    raw_json = Column(JSONB, nullable=False)

    health = relationship("HealthDeclaration", back_populates="document", uselist=False, cascade="all, delete-orphan")
    health_questions = relationship("HealthQuestion", back_populates="document", cascade="all, delete-orphan")
    health_ports_of_call = relationship("HealthPortOfCall", back_populates="document", cascade="all, delete-orphan")
    health_crew_joined = relationship("HealthCrewJoined", back_populates="document", cascade="all, delete-orphan")

    dgm = relationship("DGMDeclaration", back_populates="document", uselist=False, cascade="all, delete-orphan")
    dgm_cargo_items = relationship("DGMCargoItem", back_populates="document", cascade="all, delete-orphan")

    dgd = relationship("DGDDeclaration", back_populates="document", uselist=False, cascade="all, delete-orphan")
    dgd_matrix_rows = relationship("DGDMatrixRow", back_populates="document", cascade="all, delete-orphan")

    alerts = relationship("Alert", back_populates="document", cascade="all, delete-orphan")


class HealthDeclaration(Base):
    __tablename__ = "health_declarations"

    document_id = Column(BigInteger, ForeignKey("documents.document_id", ondelete="CASCADE"), primary_key=True)
    submitted_port = Column(Text)
    submission_date = Column(Date)
    last_port = Column(Text)
    next_port = Column(Text)
    nationality = Column(Text)
    master_name = Column(Text)
    gross_tonnage = Column(Integer)
    net_tonnage = Column(Integer)
    who_affected_area = Column(Text)
    port_date_visit_area = Column(Text)
    crew_members = Column(Integer)
    passengers = Column(Text)  # peut valoir 'NIL'
    certificate_carried_on_board = Column(Text)
    certificate_date = Column(Date)
    certificate_issued_at = Column(Text)
    valid_till = Column(Date)
    re_inspection_required = Column(Text)
    water_analysis_date = Column(Date)
    water_analysis_issued_at = Column(Text)
    medical_certificate_date = Column(Date)
    medical_certificate_issued_at = Column(Text)
    fumigated_cargo = Column(Text)

    document = relationship("Document", back_populates="health")


class HealthQuestion(Base):
    __tablename__ = "health_questions"

    document_id = Column(BigInteger, ForeignKey("documents.document_id", ondelete="CASCADE"), primary_key=True)
    question_no = Column(SmallInteger, primary_key=True)
    answer = Column(Text)

    document = relationship("Document", back_populates="health_questions")


class HealthPortOfCall(Base):
    __tablename__ = "health_ports_of_call"

    id = Column(BigInteger, primary_key=True)
    document_id = Column(BigInteger, ForeignKey("documents.document_id", ondelete="CASCADE"), nullable=False)
    port = Column(Text)
    date_of_departure = Column(Date)

    document = relationship("Document", back_populates="health_ports_of_call")


class HealthCrewJoined(Base):
    __tablename__ = "health_crew_joined"

    id = Column(BigInteger, primary_key=True)
    document_id = Column(BigInteger, ForeignKey("documents.document_id", ondelete="CASCADE"), nullable=False)
    name = Column(Text)
    joined_at_port = Column(Text)
    date_of_joining = Column(Date)

    document = relationship("Document", back_populates="health_crew_joined")


class DGMDeclaration(Base):
    __tablename__ = "dgm_declarations"

    document_id = Column(BigInteger, ForeignKey("documents.document_id", ondelete="CASCADE"), primary_key=True)
    booking_nr = Column(Text)
    call_sign = Column(Text)
    flag_state = Column(Text)
    eta = Column(Date)
    etd = Column(Date)
    previous_port_of_call = Column(Text)
    next_port_of_call = Column(Text)
    manifest_type = Column(ARRAY(Text))

    document = relationship("Document", back_populates="dgm")


class DGMCargoItem(Base):
    __tablename__ = "dgm_cargo_items"

    id = Column(BigInteger, primary_key=True)
    document_id = Column(BigInteger, ForeignKey("documents.document_id", ondelete="CASCADE"), nullable=False)
    container_number = Column(Text)
    technical_name = Column(Text)
    class_ = Column("class", Text)
    un_number = Column(Text)
    quantity = Column(Text)
    unite = Column(Text)
    net_weight = Column(Text)
    stowage_position = Column(Text)
    contact_info = Column(Text)
    port = Column(Text)

    document = relationship("Document", back_populates="dgm_cargo_items")


class DGDDeclaration(Base):
    __tablename__ = "dgd_declarations"

    document_id = Column(BigInteger, ForeignKey("documents.document_id", ondelete="CASCADE"), primary_key=True)
    booking_nr = Column(Text)
    call_sign = Column(Text)
    flag_state = Column(Text)
    eta = Column(Date)
    etd = Column(Date)
    previous_port_of_call = Column(Text)
    next_port_of_call = Column(Text)

    document = relationship("Document", back_populates="dgd")


class DGDMatrixRow(Base):
    __tablename__ = "dgd_matrix"

    id = Column(BigInteger, primary_key=True)
    document_id = Column(BigInteger, ForeignKey("documents.document_id", ondelete="CASCADE"), nullable=False)
    class_ = Column("class", Text, nullable=False)
    division = Column(Text)
    to_load_main = Column(Numeric)
    to_load_transhipment = Column(Numeric)
    to_unload_main = Column(Numeric)
    to_unload_transhipment = Column(Numeric)
    in_transit = Column(Numeric)

    document = relationship("Document", back_populates="dgd_matrix_rows")


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (UniqueConstraint("document_id", "dedup_key"),)

    alert_id = Column(BigInteger, primary_key=True)
    document_id = Column(BigInteger, ForeignKey("documents.document_id", ondelete="CASCADE"), nullable=False)
    alert_type = Column(String(50), nullable=False)
    severity = Column(String(10), nullable=False, default="HIGH")
    message = Column(Text, nullable=False)
    detail = Column(JSONB)
    dedup_key = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    acknowledged = Column(Boolean, nullable=False, default=False)

    document = relationship("Document", back_populates="alerts")
