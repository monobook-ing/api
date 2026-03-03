-- Migration: extend notification_type enum with booking_success
ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'booking_success';
