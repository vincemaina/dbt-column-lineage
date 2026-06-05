select
    c.customer_id,
    c.first_name,
    count(o.order_id) as number_of_orders,
    sum(o.amount) as lifetime_value
from ANALYTICS.STAGING.STG_CUSTOMERS c
left join ANALYTICS.STAGING.STG_ORDERS o
    on c.customer_id = o.customer_id
group by 1, 2