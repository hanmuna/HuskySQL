# Wrong-prediction SQL structural analysis (5 failed questions)

## idx 1 (qid 1, california_schools, moderate)

```sql
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
```

- **relational algebra**: τ_{EligibleFreeRate ASC}^{3} ( π_{CDSCode, School Name, (Free Meal Count (Ages 5-17)*1.0 / Enrollment (Ages 5-17)) → EligibleFreeRate} ( σ_{School Type = 'Continuation School' ∧ Enrollment (Ages 5-17) IS NOT NULL ∧ Enrollment (Ages 5-17) > 0 ∧ Free Meal Count (Ages 5-17) IS NOT NULL} (frpm) ) )
- **nl**: Returns the three continuation schools with the lowest proportion of enrolled students (ages 5–17) eligible for free meals, excluding rows with missing or zero enrollment values.

<details><summary>BNF derivation</summary>

```
<query> ::= SELECT <proj> FROM <table> WHERE <cond> ORDER BY <expr> ASC LIMIT <num>
<proj> ::= <col>, <col>, (<col> * <num> / <col>) AS <alias>
<cond> ::= <cond> AND <cond> | <col> = <literal> | <col> IS NOT NULL | <col> > <num>
<table> ::= frpm
```
</details>

---

## idx 2 (qid 2, california_schools, simple)

```sql
Select distinct zip codes from the `schools` table.

Here is the correct SQLite query:


SELECT DISTINCT s.Zip
FROM frpm f
JOIN schools s
  ON f.CDSCode = s.CDSCode
WHERE f.`Charter School (Y/N)` = 1
  AND f.`District Name` = 'Fresno County Office of Education'
```

- **parse_error**: `ParseError: Invalid expression / Unexpected token. Line 1, Col: 50.
  Select distinct zip codes from the `schools` [4mtable[0m.

Here is the correct SQLite query:


SELECT DISTINCT s.Zip
FROM frpm f
JOIN schools s
  ON f.CDSCo`
- **relational algebra**: π_{s.Zip}(σ_{f.`Charter School (Y/N)` = 1 ∧ f.`District Name` = 'Fresno County Office of Education'}(frpm ⋈_{f.CDSCode = s.CDSCode} schools))
- **nl**: Returns the distinct zip codes of schools that are charter schools and belong to the Fresno County Office of Education district.

<details><summary>BNF derivation</summary>

```
<query> ::= SELECT DISTINCT <proj> FROM <rel> JOIN <rel> ON <cond> WHERE <cond>
<proj> ::= s.Zip
<rel> ::= frpm | schools
<cond> ::= <cond> AND <cond> | f.CDSCode = s.CDSCode | f.`Charter School (Y/N)` = 1 | f.`District Name` = 'Fresno County Office of Education'
```
</details>

---

## idx 3 (qid 3, california_schools, simple)

```sql
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
```

- **parse_error**: `ParseError: Invalid expression / Unexpected token. Line 1, Col: 32.
  Select the unabbreviated [4mmailing[0m address fields (`MailStreet`, `MailCity`, `MailState`, `MailZip`).
4. Order descending and limit to`
- **relational algebra**: π_{MailStreet, MailCity, MailState, MailZip}( τ_{FRPM Count (K-12) DESC} ( frpm ⋈_{frpm.CDSCode = schools.CDSCode} schools ) ) [limit 1]
- **nl**: The query returns the mailing address of the school with the highest FRPM Count (K-12).

<details><summary>BNF derivation</summary>

```
<query> ::= SELECT <proj> FROM <rel> JOIN <rel> ON <cond> ORDER BY <col> DESC LIMIT <num>
<proj> ::= <col>, <col>, <col>, <col>
<rel> ::= frpm | schools
<cond> ::= <col> = <col>
```
</details>

---

## idx 6 (qid 6, california_schools, simple)

```sql
Select the school name.


SELECT s.School
FROM satscores AS sat
JOIN schools AS s
    ON sat.cds = s.CDSCode
WHERE sat.NumTstTakr > 500
  AND s.Magnet = 1
```

- **parse_error**: `ParseError: Invalid expression / Unexpected token. Line 1, Col: 22.
  Select the school [4mname[0m.


SELECT s.School
FROM satscores AS sat
JOIN schools AS s
    ON sat.cds = s.CDSCode
WHERE sat.Num`
- **relational algebra**: π_{s.School}(σ_{sat.NumTstTakr > 500 ∧ s.Magnet = 1}(satscores ⋈_{sat.cds = s.CDSCode} schools))
- **nl**: Returns the names of schools that are magnet schools and have more than 500 SAT test takers.

<details><summary>BNF derivation</summary>

```
<query> ::= SELECT <proj> FROM <join> WHERE <cond>
<proj> ::= <column>
<join> ::= <table> JOIN <table> ON <predicate>
<cond> ::= <predicate> AND <predicate>
<predicate> ::= <column> > <value> | <column> = <value>
```
</details>

---

## idx 9 (qid 9, california_schools, simple)

```sql
SELECT COUNT(*)
FROM satscores s
JOIN schools sc
  ON s.cds = sc.CDSCode
WHERE s.AvgScrMath > 560
  AND sc.FundingType = 'Directly Funded'
```

- **relational algebra**: γ_{COUNT(*)}(σ_{s.AvgScrMath > 560 ∧ sc.FundingType = 'Directly Funded'}(s ⋈_{s.cds = sc.CDSCode} sc))
- **nl**: Counts the number of joined sat score and school records where the math average exceeds 560 and the school is directly funded.

<details><summary>BNF derivation</summary>

```
<query> ::= SELECT <agg> FROM <join> WHERE <cond>
<agg> ::= COUNT ( * )
<join> ::= <rel> JOIN <rel> ON <join_cond>
<cond> ::= <cond> AND <cond>
<cond> ::= <attr> > <const> | <attr> = <const>
```
</details>

---

