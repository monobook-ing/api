-- Migration: add currency support for room and booking prices
-- Run this on existing databases that already have init_db.sql applied

CREATE TABLE IF NOT EXISTS currencies (
  code TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  display TEXT NOT NULL
);

INSERT INTO currencies (code, name, display) VALUES
  ('AED', 'UAE Dirham', 'AED'),
  ('AFN', 'Afghan Afghani', 'AFN'),
  ('ALL', 'Albanian Lek', 'ALL'),
  ('AMD', 'Armenian Dram', 'AMD'),
  ('ANG', 'Netherlands Antillean Guilder', 'ANG'),
  ('AOA', 'Angolan Kwanza', 'AOA'),
  ('ARS', 'Argentine Peso', 'ARS'),
  ('AUD', 'Australian Dollar', 'A$'),
  ('AWG', 'Aruban Florin', 'AWG'),
  ('AZN', 'Azerbaijani Manat', 'AZN'),
  ('BAM', 'Bosnia and Herzegovina Convertible Mark', 'BAM'),
  ('BBD', 'Barbadian Dollar', 'BBD'),
  ('BDT', 'Bangladeshi Taka', 'BDT'),
  ('BGN', 'Bulgarian Lev', 'BGN'),
  ('BHD', 'Bahraini Dinar', 'BHD'),
  ('BIF', 'Burundian Franc', 'BIF'),
  ('BMD', 'Bermudian Dollar', 'BMD'),
  ('BND', 'Brunei Dollar', 'BND'),
  ('BOB', 'Bolivian Boliviano', 'BOB'),
  ('BRL', 'Brazilian Real', 'R$'),
  ('BSD', 'Bahamian Dollar', 'BSD'),
  ('BTN', 'Bhutanese Ngultrum', 'BTN'),
  ('BWP', 'Botswana Pula', 'BWP'),
  ('BYN', 'Belarusian Ruble', 'BYN'),
  ('BZD', 'Belize Dollar', 'BZD'),
  ('CAD', 'Canadian Dollar', 'C$'),
  ('CDF', 'Congolese Franc', 'CDF'),
  ('CHF', 'Swiss Franc', 'CHF'),
  ('CLP', 'Chilean Peso', 'CLP'),
  ('CNY', 'Chinese Yuan', 'CN¥'),
  ('COP', 'Colombian Peso', 'COP'),
  ('CRC', 'Costa Rican Colon', 'CRC'),
  ('CUP', 'Cuban Peso', 'CUP'),
  ('CVE', 'Cape Verdean Escudo', 'CVE'),
  ('CZK', 'Czech Koruna', 'CZK'),
  ('DJF', 'Djiboutian Franc', 'DJF'),
  ('DKK', 'Danish Krone', 'DKK'),
  ('DOP', 'Dominican Peso', 'DOP'),
  ('DZD', 'Algerian Dinar', 'DZD'),
  ('EGP', 'Egyptian Pound', 'EGP'),
  ('ERN', 'Eritrean Nakfa', 'ERN'),
  ('ETB', 'Ethiopian Birr', 'ETB'),
  ('EUR', 'Euro', '€'),
  ('FJD', 'Fijian Dollar', 'FJD'),
  ('FKP', 'Falkland Islands Pound', 'FKP'),
  ('GBP', 'Pound Sterling', '£'),
  ('GEL', 'Georgian Lari', 'GEL'),
  ('GHS', 'Ghanaian Cedi', 'GHS'),
  ('GIP', 'Gibraltar Pound', 'GIP'),
  ('GMD', 'Gambian Dalasi', 'GMD'),
  ('GNF', 'Guinean Franc', 'GNF'),
  ('GTQ', 'Guatemalan Quetzal', 'GTQ'),
  ('GYD', 'Guyanese Dollar', 'GYD'),
  ('HKD', 'Hong Kong Dollar', 'HK$'),
  ('HNL', 'Honduran Lempira', 'HNL'),
  ('HRK', 'Croatian Kuna', 'HRK'),
  ('HTG', 'Haitian Gourde', 'HTG'),
  ('HUF', 'Hungarian Forint', 'HUF'),
  ('IDR', 'Indonesian Rupiah', 'IDR'),
  ('ILS', 'Israeli New Shekel', '₪'),
  ('INR', 'Indian Rupee', '₹'),
  ('IQD', 'Iraqi Dinar', 'IQD'),
  ('IRR', 'Iranian Rial', 'IRR'),
  ('ISK', 'Icelandic Krona', 'ISK'),
  ('JMD', 'Jamaican Dollar', 'JMD'),
  ('JOD', 'Jordanian Dinar', 'JOD'),
  ('JPY', 'Japanese Yen', '¥'),
  ('KES', 'Kenyan Shilling', 'KES'),
  ('KGS', 'Kyrgyzstani Som', 'KGS'),
  ('KHR', 'Cambodian Riel', 'KHR'),
  ('KMF', 'Comorian Franc', 'KMF'),
  ('KPW', 'North Korean Won', 'KPW'),
  ('KRW', 'South Korean Won', '₩'),
  ('KWD', 'Kuwaiti Dinar', 'KWD'),
  ('KYD', 'Cayman Islands Dollar', 'KYD'),
  ('KZT', 'Kazakhstani Tenge', 'KZT'),
  ('LAK', 'Lao Kip', 'LAK'),
  ('LBP', 'Lebanese Pound', 'LBP'),
  ('LKR', 'Sri Lankan Rupee', 'LKR'),
  ('LRD', 'Liberian Dollar', 'LRD'),
  ('LSL', 'Lesotho Loti', 'LSL'),
  ('LYD', 'Libyan Dinar', 'LYD'),
  ('MAD', 'Moroccan Dirham', 'MAD'),
  ('MDL', 'Moldovan Leu', 'MDL'),
  ('MGA', 'Malagasy Ariary', 'MGA'),
  ('MKD', 'Macedonian Denar', 'MKD'),
  ('MMK', 'Myanmar Kyat', 'MMK'),
  ('MNT', 'Mongolian Tugrik', 'MNT'),
  ('MOP', 'Macanese Pataca', 'MOP'),
  ('MRU', 'Mauritanian Ouguiya', 'MRU'),
  ('MUR', 'Mauritian Rupee', 'MUR'),
  ('MVR', 'Maldivian Rufiyaa', 'MVR'),
  ('MWK', 'Malawian Kwacha', 'MWK'),
  ('MXN', 'Mexican Peso', 'MX$'),
  ('MYR', 'Malaysian Ringgit', 'MYR'),
  ('MZN', 'Mozambican Metical', 'MZN'),
  ('NAD', 'Namibian Dollar', 'NAD'),
  ('NGN', 'Nigerian Naira', 'NGN'),
  ('NIO', 'Nicaraguan Cordoba', 'NIO'),
  ('NOK', 'Norwegian Krone', 'NOK'),
  ('NPR', 'Nepalese Rupee', 'NPR'),
  ('NZD', 'New Zealand Dollar', 'NZ$'),
  ('OMR', 'Omani Rial', 'OMR'),
  ('PAB', 'Panamanian Balboa', 'PAB'),
  ('PEN', 'Peruvian Sol', 'PEN'),
  ('PGK', 'Papua New Guinean Kina', 'PGK'),
  ('PHP', 'Philippine Peso', 'PHP'),
  ('PKR', 'Pakistani Rupee', 'PKR'),
  ('PLN', 'Polish Zloty', 'PLN'),
  ('PYG', 'Paraguayan Guarani', 'PYG'),
  ('QAR', 'Qatari Riyal', 'QAR'),
  ('RON', 'Romanian Leu', 'RON'),
  ('RSD', 'Serbian Dinar', 'RSD'),
  ('RUB', 'Russian Ruble', '₽'),
  ('RWF', 'Rwandan Franc', 'RWF'),
  ('SAR', 'Saudi Riyal', 'SAR'),
  ('SBD', 'Solomon Islands Dollar', 'SBD'),
  ('SCR', 'Seychellois Rupee', 'SCR'),
  ('SDG', 'Sudanese Pound', 'SDG'),
  ('SEK', 'Swedish Krona', 'SEK'),
  ('SGD', 'Singapore Dollar', 'S$'),
  ('SHP', 'Saint Helena Pound', 'SHP'),
  ('SLE', 'Sierra Leonean Leone', 'SLE'),
  ('SOS', 'Somali Shilling', 'SOS'),
  ('SRD', 'Surinamese Dollar', 'SRD'),
  ('SSP', 'South Sudanese Pound', 'SSP'),
  ('STN', 'Sao Tome and Principe Dobra', 'STN'),
  ('SVC', 'Salvadoran Colon', 'SVC'),
  ('SYP', 'Syrian Pound', 'SYP'),
  ('SZL', 'Eswatini Lilangeni', 'SZL'),
  ('THB', 'Thai Baht', '฿'),
  ('TJS', 'Tajikistani Somoni', 'TJS'),
  ('TMT', 'Turkmenistani Manat', 'TMT'),
  ('TND', 'Tunisian Dinar', 'TND'),
  ('TOP', 'Tongan Paanga', 'TOP'),
  ('TRY', 'Turkish Lira', '₺'),
  ('TTD', 'Trinidad and Tobago Dollar', 'TTD'),
  ('TWD', 'New Taiwan Dollar', 'NT$'),
  ('TZS', 'Tanzanian Shilling', 'TZS'),
  ('UAH', 'Ukrainian Hryvnia', 'UAH'),
  ('UGX', 'Ugandan Shilling', 'UGX'),
  ('USD', 'US Dollar', '$'),
  ('UYU', 'Uruguayan Peso', 'UYU'),
  ('UZS', 'Uzbekistani Som', 'UZS'),
  ('VES', 'Venezuelan Bolivar', 'VES'),
  ('VND', 'Vietnamese Dong', 'VND'),
  ('VUV', 'Vanuatu Vatu', 'VUV'),
  ('WST', 'Samoan Tala', 'WST'),
  ('XAF', 'Central African CFA Franc', 'XAF'),
  ('XCD', 'East Caribbean Dollar', 'XCD'),
  ('XOF', 'West African CFA Franc', 'XOF'),
  ('XPF', 'CFP Franc', 'XPF'),
  ('YER', 'Yemeni Rial', 'YER'),
  ('ZAR', 'South African Rand', 'ZAR'),
  ('ZMW', 'Zambian Kwacha', 'ZMW'),
  ('ZWL', 'Zimbabwean Dollar', 'ZWL')
ON CONFLICT (code) DO UPDATE
SET
  name = EXCLUDED.name,
  display = EXCLUDED.display;

ALTER TABLE rooms
  ADD COLUMN IF NOT EXISTS currency_code TEXT;

UPDATE rooms
SET currency_code = 'USD'
WHERE currency_code IS NULL;

ALTER TABLE rooms
  ALTER COLUMN currency_code SET DEFAULT 'USD';

ALTER TABLE rooms
  ALTER COLUMN currency_code SET NOT NULL;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'rooms_currency_code_fkey'
  ) THEN
    ALTER TABLE rooms
      ADD CONSTRAINT rooms_currency_code_fkey
      FOREIGN KEY (currency_code) REFERENCES currencies(code);
  END IF;
END;
$$;

CREATE INDEX IF NOT EXISTS idx_rooms_currency_code ON rooms(currency_code);

ALTER TABLE bookings
  ADD COLUMN IF NOT EXISTS currency_code TEXT;

UPDATE bookings b
SET currency_code = COALESCE(r.currency_code, 'USD')
FROM rooms r
WHERE b.room_id = r.id
  AND b.currency_code IS NULL;

UPDATE bookings
SET currency_code = 'USD'
WHERE currency_code IS NULL;

ALTER TABLE bookings
  ALTER COLUMN currency_code SET DEFAULT 'USD';

ALTER TABLE bookings
  ALTER COLUMN currency_code SET NOT NULL;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'bookings_currency_code_fkey'
  ) THEN
    ALTER TABLE bookings
      ADD CONSTRAINT bookings_currency_code_fkey
      FOREIGN KEY (currency_code) REFERENCES currencies(code);
  END IF;
END;
$$;

CREATE INDEX IF NOT EXISTS idx_bookings_currency_code ON bookings(currency_code);
