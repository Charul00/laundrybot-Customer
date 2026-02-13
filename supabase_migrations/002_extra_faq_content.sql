-- Optional: Add more FAQ/policy content for RAG. Run in Supabase SQL Editor.
-- After running, execute: python scripts/fill_faq_embeddings.py

insert into faq_documents (content)
values
('Standard wash costs around Rs 50. Dry cleaning Rs 120. Ironing Rs 15. Shoe cleaning Rs 200. Prices may vary by cloth type.'),
('We offer Wash only, Wash with Iron, Dry clean, and Shoe clean. You can choose one or combine services.'),
('Express delivery is available for an additional 30 percent fee. Standard delivery is about 48 hours.'),
('Same day or next day express delivery can be arranged for an extra charge.'),
('Shoe cleaning usually takes about 48 hours. We handle sneakers, leather shoes, and formal shoes.'),
('Rewash is free if you report the issue within 24 hours of delivery. Contact the outlet or reply here.'),
('For complaints, please share your Order ID and the issue. We will resolve it within 24-48 hours.'),
('Pickup and delivery can be scheduled from your address. We serve Pune areas.'),
('Payment can be made at pickup, at delivery, or via our app. We accept cash and UPI.'),
('Laundry Central has outlets at Downtown, West City, and East Market. Your order is assigned to the nearest outlet.');
