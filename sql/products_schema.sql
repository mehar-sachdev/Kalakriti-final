-- Reference schema for the LEGACY storefront tables (products/orders), for a Supabase project
-- where you want Supabase itself (rather than the local catalogue fallback) to be the source of
-- truth for /products and /orders. This is a SEPARATE, public-schema concern from the RAG vector
-- store, which manages its own private "rag" schema (see supabase/migrations/).
--
-- Not required to run the site or the AI assistant - both work from the local catalogue
-- (data/metadata/products.json) without this. Only needed if you want real checkout via /orders.
--
-- Usage: paste into the Supabase SQL editor, then `python scripts/seed_database.py`.

create table if not exists public.artisans (
    artisan_id       text primary key,
    artisan_name     text not null,
    craft            text,
    state            text,
    experience_years integer,
    rating           numeric,
    payment_status   text default 'Pending'
);

create table if not exists public.products (
    product_id     integer primary key,
    product_name   text not null,
    region         text,
    craft          text,
    material       text,
    technique      text,
    origin         text,
    artisan_id     text references public.artisans(artisan_id),
    price          numeric not null,
    rating         numeric,
    stock_quantity integer not null default 0,
    image_url      text,
    description    text,
    status         text default 'Active'
);

create table if not exists public.orders (
    order_id       text primary key,
    customer_id    text not null,
    total_amount   numeric not null,
    shipping_city  text,
    shipping_state text,
    order_status   text default 'Pending',
    payment_status text default 'Pending',
    created_at     timestamptz not null default now()
);

create table if not exists public.order_items (
    id         bigserial primary key,
    order_id   text references public.orders(order_id),
    product_id integer references public.products(product_id),
    quantity   integer not null,
    unit_price numeric not null,
    subtotal   numeric not null
);

create table if not exists public.inventory_transactions (
    id                bigserial primary key,
    product_id        integer references public.products(product_id),
    order_id          text references public.orders(order_id),
    transaction_type  text,
    quantity_change   integer,
    notes             text,
    created_at        timestamptz not null default now()
);
