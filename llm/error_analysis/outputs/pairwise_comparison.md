# Pred vs Gold — pairwise BNF / AST / relational-algebra comparison

5 failed questions. For each: the predicted (wrong) SQL on the left, the gold SQL on the right, compared across all three representations.

## idx 1  ·  california_schools  ·  moderate

> Returns the three continuation schools with the lowest proportion of enrolled students (ages 5–17) eligible for free meals, excluding rows with missing or zero enrollment values.

**SQL**

```sql
-- PRED (wrong)
SELECT 
    CDSCode,
    `School Name`,
    (`Free Meal Count (Ages 5-17)` * 1.0 / `Enrollment (Ages 5-17)`) AS EligibleFreeRate
FROM frpm
WHERE `School Type` = 'Continuation School'
  AND `Enrollment (Ages 5-17)` IS NOT NULL
  AND `Enrollment (Ages 5-17)` > 0
  AND `Free Meal Count (Ages 5-17)` IS NOT NULL
ORDER BY EligibleFreeRate ASC
LIMIT 3

-- GOLD
SELECT `Free Meal Count (Ages 5-17)` / `Enrollment (Ages 5-17)` FROM frpm WHERE `Educational Option Type` = 'Continuation School' AND `Free Meal Count (Ages 5-17)` / `Enrollment (Ages 5-17)` IS NOT NULL ORDER BY `Free Meal Count (Ages 5-17)` / `Enrollment (Ages 5-17)` ASC LIMIT 3
```

**Relational algebra**

- PRED: `τ_{EligibleFreeRate ASC}^{3} ( π_{CDSCode, School Name, (Free Meal Count (Ages 5-17)*1.0 / Enrollment (Ages 5-17)) → EligibleFreeRate} ( σ_{School Type = 'Continuation School' ∧ Enrollment (Ages 5-17) IS NOT NULL ∧ Enrollment (Ages 5-17) > 0 ∧ Free Meal Count (Ages 5-17) IS NOT NULL} (frpm) ) )`
- GOLD: `τ_{(FreeMeal/Enroll) ASC, 3}(π_{Free Meal Count (Ages 5-17)/Enrollment (Ages 5-17)}(σ_{Educational Option Type = 'Continuation School' ∧ Free Meal Count (Ages 5-17)/Enrollment (Ages 5-17) IS NOT NULL}(frpm)))`

**BNF derivation**

```
# PRED
<query> ::= SELECT <proj> FROM <table> WHERE <cond> ORDER BY <expr> ASC LIMIT <num>
<proj> ::= <col>, <col>, (<col> * <num> / <col>) AS <alias>
<cond> ::= <cond> AND <cond> | <col> = <literal> | <col> IS NOT NULL | <col> > <num>
<table> ::= frpm

# GOLD
<query> ::= SELECT <expr> FROM <table> WHERE <cond> ORDER BY <expr> ASC LIMIT <number>
<expr> ::= <col> / <col>
<cond> ::= <col> = <literal> AND <expr> IS NOT NULL
<table> ::= frpm
```

**AST node-type difference**

- only in PRED: Identifier×3, Column×2, Literal×2, And×2, Alias×1, Paren×1, Not×1, Mul×1, GT×1, Is×1, Null×1
- only in GOLD: Div×2

**Clause-level diff:** SELECT, WHERE, ORDER_BY

---

## idx 2  ·  california_schools  ·  simple

> Returns the distinct zip codes of schools that are charter schools and belong to the Fresno County Office of Education district.

**SQL**

```sql
-- PRED (wrong)
Select distinct zip codes from the `schools` table.

Here is the correct SQLite query:


SELECT DISTINCT s.Zip
FROM frpm f
JOIN schools s
  ON f.CDSCode = s.CDSCode
WHERE f.`Charter School (Y/N)` = 1
  AND f.`District Name` = 'Fresno County Office of Education'

-- GOLD
SELECT T2.Zip FROM frpm AS T1 INNER JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode WHERE T1.`District Name` = 'Fresno County Office of Education' AND T1.`Charter School (Y/N)` = 1
```

**Relational algebra**

- PRED: `π_{s.Zip}(σ_{f.`Charter School (Y/N)` = 1 ∧ f.`District Name` = 'Fresno County Office of Education'}(frpm ⋈_{f.CDSCode = s.CDSCode} schools))`
- GOLD: `π_{T2.Zip}(σ_{T1.District Name = 'Fresno County Office of Education' ∧ T1.Charter School (Y/N) = 1}((ρ_{T1}(frpm)) ⋈_{T1.CDSCode = T2.CDSCode} (ρ_{T2}(schools))))`

**BNF derivation**

```
# PRED
<query> ::= SELECT DISTINCT <proj> FROM <rel> JOIN <rel> ON <cond> WHERE <cond>
<proj> ::= s.Zip
<rel> ::= frpm | schools
<cond> ::= <cond> AND <cond> | f.CDSCode = s.CDSCode | f.`Charter School (Y/N)` = 1 | f.`District Name` = 'Fresno County Office of Education'

# GOLD
<query> ::= SELECT <proj> FROM <rel> WHERE <cond>
<proj> ::= <column>
<rel> ::= <table> INNER JOIN <table> ON <join_cond>
<cond> ::= <cond> AND <cond>
<cond> ::= <column> = <value>
```

**AST node-type difference**

- only in PRED: —
- only in GOLD: Identifier×14, Column×5, EQ×3, Table×2, TableAlias×2, Literal×2, Select×1, From×1, Join×1, Where×1, And×1

**Clause-level diff:** SELECT, DISTINCT, AGGREGATION, FROM, JOIN, WHERE, GROUP_BY, HAVING, ORDER_BY, SUBQUERY, SET_OP, FUNCTION, CAST

---

## idx 3  ·  california_schools  ·  simple

> The query returns the mailing address of the school with the highest FRPM Count (K-12).

**SQL**

```sql
-- PRED (wrong)
Select the unabbreviated mailing address fields (`MailStreet`, `MailCity`, `MailState`, `MailZip`).
4. Order descending and limit to 1.


SELECT 
    s.MailStreet,
    s.MailCity,
    s.MailState,
    s.MailZip
FROM frpm f
JOIN schools s
    ON f.CDSCode = s.CDSCode
ORDER BY f."FRPM Count (K-12)" DESC
LIMIT 1

-- GOLD
SELECT T2.MailStreet FROM frpm AS T1 INNER JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode ORDER BY T1.`FRPM Count (K-12)` DESC LIMIT 1
```

**Relational algebra**

- PRED: `π_{MailStreet, MailCity, MailState, MailZip}( τ_{FRPM Count (K-12) DESC} ( frpm ⋈_{frpm.CDSCode = schools.CDSCode} schools ) ) [limit 1]`
- GOLD: `π_{T2.MailStreet}( τ_{T1.`FRPM Count (K-12)` DESC}( T1 ⋈_{T1.CDSCode = T2.CDSCode} T2 ) ) LIMIT 1`

**BNF derivation**

```
# PRED
<query> ::= SELECT <proj> FROM <rel> JOIN <rel> ON <cond> ORDER BY <col> DESC LIMIT <num>
<proj> ::= <col>, <col>, <col>, <col>
<rel> ::= frpm | schools
<cond> ::= <col> = <col>

# GOLD
<query> ::= SELECT <proj> FROM <from> ORDER BY <col> DESC LIMIT <num>
<proj> ::= <col>
<from> ::= <table> INNER JOIN <table> ON <cond>
<cond> ::= <col> = <col>
```

**AST node-type difference**

- only in PRED: —
- only in GOLD: Identifier×12, Column×4, Table×2, TableAlias×2, Select×1, Limit×1, From×1, Join×1, Order×1, Literal×1, EQ×1, Ordered×1

**Clause-level diff:** SELECT, DISTINCT, AGGREGATION, FROM, JOIN, WHERE, GROUP_BY, HAVING, ORDER_BY, LIMIT, SUBQUERY, SET_OP, FUNCTION, CAST

---

## idx 6  ·  california_schools  ·  simple

> Returns the names of schools that are magnet schools and have more than 500 SAT test takers.

**SQL**

```sql
-- PRED (wrong)
Select the school name.


SELECT s.School
FROM satscores AS sat
JOIN schools AS s
    ON sat.cds = s.CDSCode
WHERE sat.NumTstTakr > 500
  AND s.Magnet = 1

-- GOLD
SELECT T2.School FROM satscores AS T1 INNER JOIN schools AS T2 ON T1.cds = T2.CDSCode WHERE T2.Magnet = 1 AND T1.NumTstTakr > 500
```

**Relational algebra**

- PRED: `π_{s.School}(σ_{sat.NumTstTakr > 500 ∧ s.Magnet = 1}(satscores ⋈_{sat.cds = s.CDSCode} schools))`
- GOLD: `π_{T2.School}(σ_{T2.Magnet = 1 ∧ T1.NumTstTakr > 500}(T1 ⋈_{T1.cds = T2.CDSCode} T2))`

**BNF derivation**

```
# PRED
<query> ::= SELECT <proj> FROM <join> WHERE <cond>
<proj> ::= <column>
<join> ::= <table> JOIN <table> ON <predicate>
<cond> ::= <predicate> AND <predicate>
<predicate> ::= <column> > <value> | <column> = <value>

# GOLD
<query> ::= SELECT <proj> FROM <rel> WHERE <cond>
<proj> ::= T2.School
<rel> ::= satscores AS T1 INNER JOIN schools AS T2 ON <join_cond>
<join_cond> ::= T1.cds = T2.CDSCode
<cond> ::= T2.Magnet = 1 AND T1.NumTstTakr > 500
```

**AST node-type difference**

- only in PRED: —
- only in GOLD: Identifier×14, Column×5, Table×2, EQ×2, TableAlias×2, Literal×2, Select×1, From×1, Join×1, Where×1, And×1, GT×1

**Clause-level diff:** SELECT, DISTINCT, AGGREGATION, FROM, JOIN, WHERE, GROUP_BY, HAVING, ORDER_BY, SUBQUERY, SET_OP, FUNCTION, CAST

---

## idx 9  ·  california_schools  ·  simple

> Counts the number of joined sat score and school records where the math average exceeds 560 and the school is directly funded.

**SQL**

```sql
-- PRED (wrong)
SELECT COUNT(*)
FROM satscores s
JOIN schools sc
  ON s.cds = sc.CDSCode
WHERE s.AvgScrMath > 560
  AND sc.FundingType = 'Directly Funded'

-- GOLD
SELECT COUNT(T2.`School Code`) FROM satscores AS T1 INNER JOIN frpm AS T2 ON T1.cds = T2.CDSCode WHERE T1.AvgScrMath > 560 AND T2.`Charter Funding Type` = 'Directly funded'
```

**Relational algebra**

- PRED: `γ_{COUNT(*)}(σ_{s.AvgScrMath > 560 ∧ sc.FundingType = 'Directly Funded'}(s ⋈_{s.cds = sc.CDSCode} sc))`
- GOLD: `γ COUNT(T2.`School Code`) ( σ_{T1.AvgScrMath > 560 ∧ T2.`Charter Funding Type` = 'Directly funded'} ( T1 ⋈_{T1.cds = T2.CDSCode} T2 ) )`

**BNF derivation**

```
# PRED
<query> ::= SELECT <agg> FROM <join> WHERE <cond>
<agg> ::= COUNT ( * )
<join> ::= <rel> JOIN <rel> ON <join_cond>
<cond> ::= <cond> AND <cond>
<cond> ::= <attr> > <const> | <attr> = <const>

# GOLD
<query> ::= SELECT <agg> FROM <rel> INNER JOIN <rel> ON <cond> WHERE <cond>
<agg> ::= COUNT ( <column> )
<rel> ::= satscores AS T1 | frpm AS T2
<cond> ::= <cond> AND <cond> | <column> > <value> | <column> = <value>
```

**AST node-type difference**

- only in PRED: Star×1
- only in GOLD: Identifier×2, Column×1

**Clause-level diff:** SELECT, FROM, WHERE

---

