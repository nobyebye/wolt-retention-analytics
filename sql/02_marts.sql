-- Full refresh inside the transaction managed by the Python pipeline.
DELETE FROM mart_retention;
INSERT INTO mart_retention
WITH RECURSIVE months AS (
 SELECT MIN(cohort_month) AS month_start FROM dim_customer
 UNION ALL
 SELECT DATE_ADD(month_start, INTERVAL 1 MONTH) FROM months
 WHERE DATE_ADD(month_start, INTERVAL 1 MONTH) <= (SELECT as_of_date FROM analysis_config WHERE id=1)
), cohorts AS (
 SELECT cohort_month, acquisition_line, COUNT(*) AS cohort_users
 FROM dim_customer GROUP BY cohort_month, acquisition_line
), active AS (
 SELECT c.cohort_month, c.acquisition_line,
 CAST(DATE_FORMAT(p.purchase_date, '%Y-%m-01') AS DATE) AS activity_month,
 COUNT(DISTINCT p.user_id) AS platform_active,
 COUNT(DISTINCT CASE WHEN p.product_line=c.acquisition_line THEN p.user_id END) AS same_line_active
 FROM fact_purchase p JOIN dim_customer c ON p.user_id=c.user_id
 GROUP BY c.cohort_month,c.acquisition_line,activity_month
), grid AS (
 SELECT c.*, m.month_start, TIMESTAMPDIFF(MONTH,c.cohort_month,m.month_start) AS month_number,
 (m.month_start >= cfg.observation_start AND LAST_DAY(m.month_start) <= cfg.as_of_date) AS eligible,
 COALESCE(a.platform_active,0) AS platform_active, COALESCE(a.same_line_active,0) AS same_line_active
 FROM cohorts c JOIN months m ON m.month_start >= c.cohort_month
 CROSS JOIN analysis_config cfg
 LEFT JOIN active a ON a.cohort_month=c.cohort_month AND a.acquisition_line=c.acquisition_line AND a.activity_month=m.month_start
)
SELECT cohort_month, acquisition_line, month_number, month_start, cohort_users, eligible,
 CASE WHEN eligible THEN platform_active END, CASE WHEN eligible THEN same_line_active END,
 CASE WHEN eligible THEN platform_active/cohort_users END,
 CASE WHEN eligible THEN same_line_active/cohort_users END FROM grid;

DELETE FROM mart_repurchase;
INSERT INTO mart_repurchase
WITH eligible AS (
 SELECT c.* FROM dim_customer c CROSS JOIN analysis_config cfg
 WHERE c.first_purchase_date >= cfg.observation_start
 AND DATE_ADD(c.first_purchase_date, INTERVAL 30 DAY) <= cfg.as_of_date
), per_user AS (
 SELECT c.user_id,c.acquisition_line,
 MAX(CASE WHEN p.purchase_id IS NOT NULL THEN 1 ELSE 0 END) AS repeated,
 MAX(CASE WHEN p.product_line<>c.acquisition_line THEN 1 ELSE 0 END) AS crossed
 FROM eligible c LEFT JOIN fact_purchase p ON c.user_id=p.user_id
 AND p.purchase_id<>c.first_purchase_id
 AND p.purchase_date BETWEEN c.first_purchase_date AND DATE_ADD(c.first_purchase_date, INTERVAL 30 DAY)
 GROUP BY c.user_id,c.acquisition_line
)
SELECT acquisition_line,COUNT(*),SUM(repeated),SUM(crossed),AVG(repeated),AVG(crossed)
FROM per_user GROUP BY acquisition_line;

DELETE FROM mart_monthly;
INSERT INTO mart_monthly
SELECT CAST(DATE_FORMAT(p.purchase_date,'%Y-%m-01') AS DATE) AS activity_month,
 p.product_line,COUNT(*),COUNT(DISTINCT p.user_id)
FROM fact_purchase p CROSS JOIN analysis_config cfg
WHERE CAST(DATE_FORMAT(p.purchase_date,'%Y-%m-01') AS DATE)>=cfg.observation_start
 AND LAST_DAY(p.purchase_date)<=cfg.as_of_date
GROUP BY activity_month,p.product_line;
