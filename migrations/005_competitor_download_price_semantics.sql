UPDATE competitors
SET price_type = 'free_download'
WHERE current_price = 0
  AND platform IN ('app_store', 'google_play');

UPDATE competitors
SET price_type = 'upfront_download'
WHERE current_price > 0
  AND platform IN ('app_store', 'google_play')
  AND (price_type IS NULL OR price_type = 'app_purchase');
