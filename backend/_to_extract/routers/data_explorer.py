from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import date, datetime
import csv
import io

from core.database import get_db
from models import KBPrice, Transaction, Listing

router = APIRouter()


# Pydantic schemas
class KBPriceSchema(BaseModel):
    id: int
    complex_id: int
    area_id: int
    as_of_date: date
    general_price: Optional[int]
    high_avg_price: Optional[int]
    low_avg_price: Optional[int]
    fetched_at: datetime

    class Config:
        from_attributes = True


class TransactionSchema(BaseModel):
    id: int
    complex_id: int
    contract_date: date
    price: int
    exclusive_m2: float
    floor: Optional[int]
    source: str

    class Config:
        from_attributes = True


class ListingSchema(BaseModel):
    id: int
    complex_id: int
    source_listing_id: str
    ask_price: int
    exclusive_m2: Optional[float]
    floor: Optional[int]
    status: str
    fetched_at: datetime

    class Config:
        from_attributes = True


@router.get("/kb-prices", response_model=List[KBPriceSchema])
def get_kb_prices(
    complex_id: Optional[int] = None,
    area_id: Optional[int] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """KB 시세 데이터 조회"""
    query = db.query(KBPrice)
    
    if complex_id:
        query = query.filter(KBPrice.complex_id == complex_id)
    if area_id:
        query = query.filter(KBPrice.area_id == area_id)
    if from_date:
        query = query.filter(KBPrice.as_of_date >= from_date)
    if to_date:
        query = query.filter(KBPrice.as_of_date <= to_date)
    
    prices = query.order_by(KBPrice.as_of_date.desc()).offset(skip).limit(limit).all()
    return prices


@router.get("/transactions", response_model=List[TransactionSchema])
def get_transactions(
    complex_id: Optional[int] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """실거래가 데이터 조회"""
    query = db.query(Transaction)
    
    if complex_id:
        query = query.filter(Transaction.complex_id == complex_id)
    if from_date:
        query = query.filter(Transaction.contract_date >= from_date)
    if to_date:
        query = query.filter(Transaction.contract_date <= to_date)
    
    transactions = query.order_by(Transaction.contract_date.desc()).offset(skip).limit(limit).all()
    return transactions


@router.get("/listings", response_model=List[ListingSchema])
def get_listings(
    complex_id: Optional[int] = None,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """매물 데이터 조회"""
    query = db.query(Listing)
    
    if complex_id:
        query = query.filter(Listing.complex_id == complex_id)
    if status:
        query = query.filter(Listing.status == status)
    
    listings = query.order_by(Listing.fetched_at.desc()).offset(skip).limit(limit).all()
    return listings


@router.get("/kb-prices/export")
def export_kb_prices_csv(
    complex_id: Optional[int] = None,
    area_id: Optional[int] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    db: Session = Depends(get_db),
):
    """KB 시세 데이터 CSV 내보내기"""
    query = db.query(KBPrice)
    
    if complex_id:
        query = query.filter(KBPrice.complex_id == complex_id)
    if area_id:
        query = query.filter(KBPrice.area_id == area_id)
    if from_date:
        query = query.filter(KBPrice.as_of_date >= from_date)
    if to_date:
        query = query.filter(KBPrice.as_of_date <= to_date)
    
    prices = query.all()
    
    # Create CSV
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'id', 'complex_id', 'area_id', 'as_of_date',
        'general_price', 'high_avg_price', 'low_avg_price', 'fetched_at'
    ])
    
    for price in prices:
        writer.writerow([
            price.id, price.complex_id, price.area_id, price.as_of_date,
            price.general_price, price.high_avg_price, price.low_avg_price,
            price.fetched_at
        ])
    
    output.seek(0)
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=kb_prices.csv"}
    )
