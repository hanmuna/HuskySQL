# Gold SQL structural analysis (5 failed questions)

## idx 1 (qid 1, california_schools, moderate)

```sql
SELECT `Free Meal Count (Ages 5-17)` / `Enrollment (Ages 5-17)` FROM frpm WHERE `Educational Option Type` = 'Continuation School' AND `Free Meal Count (Ages 5-17)` / `Enrollment (Ages 5-17)` IS NOT NULL ORDER BY `Free Meal Count (Ages 5-17)` / `Enrollment (Ages 5-17)` ASC LIMIT 3
```

- **relational algebra**: τ_{(FreeMeal/Enroll) ASC, 3}(π_{Free Meal Count (Ages 5-17)/Enrollment (Ages 5-17)}(σ_{Educational Option Type = 'Continuation School' ∧ Free Meal Count (Ages 5-17)/Enrollment (Ages 5-17) IS NOT NULL}(frpm)))
- **nl**: This query returns the three lowest ratios of free meal count to enrollment for continuation schools, excluding null ratios.

<details><summary>BNF derivation</summary>

```
<query> ::= SELECT <expr> FROM <table> WHERE <cond> ORDER BY <expr> ASC LIMIT <number>
<expr> ::= <col> / <col>
<cond> ::= <col> = <literal> AND <expr> IS NOT NULL
<table> ::= frpm
```
</details>

---

## idx 2 (qid 2, california_schools, simple)

```sql
SELECT T2.Zip FROM frpm AS T1 INNER JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode WHERE T1.`District Name` = 'Fresno County Office of Education' AND T1.`Charter School (Y/N)` = 1
```

- **relational algebra**: π_{T2.Zip}(σ_{T1.District Name = 'Fresno County Office of Education' ∧ T1.Charter School (Y/N) = 1}((ρ_{T1}(frpm)) ⋈_{T1.CDSCode = T2.CDSCode} (ρ_{T2}(schools))))
- **nl**: Returns the ZIP codes of schools in the Fresno County Office of Education district that are charter schools.

<details><summary>BNF derivation</summary>

```
<query> ::= SELECT <proj> FROM <rel> WHERE <cond>
<proj> ::= <column>
<rel> ::= <table> INNER JOIN <table> ON <join_cond>
<cond> ::= <cond> AND <cond>
<cond> ::= <column> = <value>
```
</details>

---

## idx 3 (qid 3, california_schools, simple)

```sql
SELECT T2.MailStreet FROM frpm AS T1 INNER JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode ORDER BY T1.`FRPM Count (K-12)` DESC LIMIT 1
```

- **relational algebra**: π_{T2.MailStreet}( τ_{T1.`FRPM Count (K-12)` DESC}( T1 ⋈_{T1.CDSCode = T2.CDSCode} T2 ) ) LIMIT 1
- **nl**: Returns the MailStreet of the school whose corresponding FRPM record has the highest FRPM Count (K-12).

<details><summary>BNF derivation</summary>

```
<query> ::= SELECT <proj> FROM <from> ORDER BY <col> DESC LIMIT <num>
<proj> ::= <col>
<from> ::= <table> INNER JOIN <table> ON <cond>
<cond> ::= <col> = <col>
```
</details>

---

## idx 6 (qid 6, california_schools, simple)

```sql
SELECT T2.School FROM satscores AS T1 INNER JOIN schools AS T2 ON T1.cds = T2.CDSCode WHERE T2.Magnet = 1 AND T1.NumTstTakr > 500
```

- **relational algebra**: π_{T2.School}(σ_{T2.Magnet = 1 ∧ T1.NumTstTakr > 500}(T1 ⋈_{T1.cds = T2.CDSCode} T2))
- **nl**: Returns the names of magnet schools that have more than 500 SAT test takers.

<details><summary>BNF derivation</summary>

```
<query> ::= SELECT <proj> FROM <rel> WHERE <cond>
<proj> ::= T2.School
<rel> ::= satscores AS T1 INNER JOIN schools AS T2 ON <join_cond>
<join_cond> ::= T1.cds = T2.CDSCode
<cond> ::= T2.Magnet = 1 AND T1.NumTstTakr > 500
```
</details>

---

## idx 9 (qid 9, california_schools, simple)

```sql
SELECT COUNT(T2.`School Code`) FROM satscores AS T1 INNER JOIN frpm AS T2 ON T1.cds = T2.CDSCode WHERE T1.AvgScrMath > 560 AND T2.`Charter Funding Type` = 'Directly funded'
```

- **relational algebra**: γ COUNT(T2.`School Code`) ( σ_{T1.AvgScrMath > 560 ∧ T2.`Charter Funding Type` = 'Directly funded'} ( T1 ⋈_{T1.cds = T2.CDSCode} T2 ) )
- **nl**: Counts the number of school codes for directly funded charter schools whose average math score is greater than 560.

<details><summary>BNF derivation</summary>

```
<query> ::= SELECT <agg> FROM <rel> INNER JOIN <rel> ON <cond> WHERE <cond>
<agg> ::= COUNT ( <column> )
<rel> ::= satscores AS T1 | frpm AS T2
<cond> ::= <cond> AND <cond> | <column> > <value> | <column> = <value>
```
</details>

---

