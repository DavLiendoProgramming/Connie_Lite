# Connie-Lite demo transcript

Provider: `template` (rule-based answers, no LLM)

## Q1. Which of Solstice's suppliers carry commodity risk, and which commodity?

*Plan:* intent `SUPPLIER_RISK`, entities `['company:solstice-robotics']`, target `None`, max_hops 2. Resolved question: "Which of Solstice's suppliers carry commodity risk, and which commodity?"

```text
(rule-based answer)
Ferrotech Alloys is a supplier to Solstice Robotics [PROFILE, a09].
The text of alert a09 does not name Solstice Robotics; this link rests on the entity annotation and the client profile [PROFILE, a09].
a09 (2026-07-31): "Ferrotech Alloys, a specialty metals supplier, warned that rare earth magnet prices have risen nearly 40% year-over-year due to export restrictions, adding cost pressure for robotics and EV motor manufacturers that rely on its precision components" [a09].
Ferrotech Alloys is exposed to rare earth magnets [a09].
```

*Gate:* `answerable` · *method:* `template` · *citations:* PROFILE, a09

<details><summary>Graph paths used</summary>

1. score 0.528
   - `Solstice Robotics -HAS_SUPPLIER-> Ferrotech Alloys  [PROFILE, a09(annotation)] (confirmed)`
   - `Ferrotech Alloys -EXPOSED_TO-> rare earth magnets  [a09(co_mention)] (discovered)`

</details>

## Q2. And what about their exposure to tariffs?

*Plan:* intent `CONNECT`, entities `['company:ferrotech-alloys']`, target `tariffs`, max_hops 2. Resolved question: "And what about Ferrotech Alloys' exposure to tariffs?"

```text
(rule-based answer)
Not found: no evidence on "tariffs" for Ferrotech Alloys in the alerts or client profile (routes through the client itself are not counted).
Closest related evidence: a09 (2026-07-31): "Ferrotech Alloys, a specialty metals supplier, warned that rare earth magnet prices have risen nearly 40% year-over-year due to export restrictions, adding cost pressure for robotics and EV motor manufacturers that rely on its precision components" [a09].
```

*Gate:* `partial` · *method:* `template` · *citations:* a09

## Q3. Are any of Solstice's competitors pushing into the same end markets as its customers?

*Plan:* intent `SHARED_MARKET`, entities `['company:solstice-robotics']`, target `None`, max_hops 2. Resolved question: "Are any of Solstice's competitors pushing into the same end markets as its customers?"

```text
(rule-based answer)
Kestrel Automation is a competitor of Solstice Robotics [PROFILE, a05, a28].
The text of alerts a05, a28 does not name Solstice Robotics; this link rests on the entity annotation and the client profile [PROFILE, a05, a28].
a05 (2026-08-09): "Kestrel Automation launched a new AI-powered vision system aimed at competing directly with warehouse automation incumbents" [a05].
a28 (2026-06-12): "Kestrel Automation announced a new distribution partnership in Europe aimed at expanding its footprint outside North America" [a28].
Kestrel Automation operates in warehouse automation [a05].
Bayview Fulfillment operates in warehouse automation [a12].
a12 (2026-07-27): "Bayview Fulfillment, a logistics and e-commerce fulfillment operator, announced plans to expand same-day delivery coverage to 40 new metro areas, adding several new automated distribution centers along the way" [a12].
Bayview Fulfillment is a customer of Solstice Robotics [PROFILE, a12].
The text of alert a12 does not name Solstice Robotics; this link rests on the entity annotation and the client profile [PROFILE, a12].
Northline Logistics operates in warehouse automation [a04].
a04 (2026-08-02): "Solstice Robotics signed a multi-year agreement to deploy its autonomous picking arms across 14 Northline Logistics distribution centers" [a04].
Northline Logistics is a customer of Solstice Robotics [PROFILE, a04].
ArcWorks Robotics is a competitor of Solstice Robotics [PROFILE, a06].
The text of alert a06 does not name Solstice Robotics; this link rests on the entity annotation and the client profile [PROFILE, a06].
a06 (2026-08-05): "ArcWorks Robotics posted a wider quarterly loss than analysts expected and announced an 8% reduction in headcount, citing softer order volumes in industrial automation" [a06].
ArcWorks Robotics operates in automotive manufacturing [a06].
Meridian Auto Group operates in automotive manufacturing [a11].
a11 (2026-08-06): "Meridian Auto Group said it will invest $2 billion over three years to automate assembly lines across its North American plants, part of a broader push to offset rising labor costs in automotive manufacturing" [a11].
Meridian Auto Group is a customer of Solstice Robotics [PROFILE, a11].
The text of alert a11 does not name Solstice Robotics; this link rests on the entity annotation and the client profile [PROFILE, a11].
Orion Freight Systems operates in warehouse automation [a22].
a22 (2026-07-25): "Orion Freight Systems, a mid-size logistics operator not previously disclosed as a Solstice customer, confirmed it has deployed Solstice Robotics picking arms across three regional distribution hubs as part of a pilot expansion" [a22].
Orion Freight Systems is a customer of Solstice Robotics (newly discovered, not in the client profile) [a22].
```

*Gate:* `answerable` · *method:* `template` · *citations:* PROFILE, a05, a28, a12, a04, a06, a11, a22

<details><summary>Graph paths used</summary>

1. score 0.352
   - `Solstice Robotics -COMPETES_WITH-> Kestrel Automation  [PROFILE, a05(annotation), a28(annotation)] (confirmed)`
   - `Kestrel Automation -OPERATES_IN-> warehouse automation  [a05(co_mention)] (discovered)`
   - `Bayview Fulfillment -OPERATES_IN-> warehouse automation  [a12(co_mention)] (discovered)`
   - `Solstice Robotics -HAS_CUSTOMER-> Bayview Fulfillment  [PROFILE, a12(annotation)] (confirmed)`
2. score 0.352
   - `Solstice Robotics -COMPETES_WITH-> Kestrel Automation  [PROFILE, a05(annotation), a28(annotation)] (confirmed)`
   - `Kestrel Automation -OPERATES_IN-> warehouse automation  [a05(co_mention)] (discovered)`
   - `Northline Logistics -OPERATES_IN-> warehouse automation  [a04(co_mention)] (discovered)`
   - `Solstice Robotics -HAS_CUSTOMER-> Northline Logistics  [PROFILE, a04(text)] (confirmed)`
3. score 0.340
   - `Solstice Robotics -COMPETES_WITH-> ArcWorks Robotics  [PROFILE, a06(annotation)] (confirmed)`
   - `ArcWorks Robotics -OPERATES_IN-> automotive manufacturing  [a06(co_mention)] (discovered)`
   - `Meridian Auto Group -OPERATES_IN-> automotive manufacturing  [a11(co_mention)] (discovered)`
   - `Solstice Robotics -HAS_CUSTOMER-> Meridian Auto Group  [PROFILE, a11(annotation)] (confirmed)`
4. score 0.317
   - `Solstice Robotics -COMPETES_WITH-> Kestrel Automation  [PROFILE, a05(annotation), a28(annotation)] (confirmed)`
   - `Kestrel Automation -OPERATES_IN-> warehouse automation  [a05(co_mention)] (discovered)`
   - `Orion Freight Systems -OPERATES_IN-> warehouse automation  [a22(co_mention)] (discovered)`
   - `Solstice Robotics -HAS_CUSTOMER-> Orion Freight Systems  [a22(text)] (discovered)`

</details>

## Q4. Does Solstice have any supplier or customer relationships that aren't in its profile?

*Plan:* intent `DISCOVERED`, entities `['company:solstice-robotics']`, target `None`, max_hops 2. Resolved question: "Does Solstice have any supplier or customer relationships that aren't in its profile?"

```text
(rule-based answer)
Hanley Precision Casting is a supplier to Solstice Robotics (newly discovered, not in the client profile) [a21].
a21 (2026-08-05): "Solstice Robotics disclosed a new manufacturing partnership with Hanley Precision Casting, a Vietnam-based components maker, to diversify its supplier base for structural robot housings amid ongoing trade tensions" [a21].
Orion Freight Systems is a customer of Solstice Robotics (newly discovered, not in the client profile) [a22].
a22 (2026-07-25): "Orion Freight Systems, a mid-size logistics operator not previously disclosed as a Solstice customer, confirmed it has deployed Solstice Robotics picking arms across three regional distribution hubs as part of a pilot expansion" [a22].
```

*Gate:* `answerable` · *method:* `template` · *citations:* a21, a22

<details><summary>Graph paths used</summary>

1. score 0.840
   - `Solstice Robotics -HAS_SUPPLIER-> Hanley Precision Casting  [a21(text)] (discovered)`
2. score 0.740
   - `Solstice Robotics -HAS_CUSTOMER-> Orion Freight Systems  [a22(text)] (discovered)`

</details>

## Q5. Could new export controls hit Solstice's supply chain?

*Plan:* intent `SUPPLIER_RISK`, entities `['company:solstice-robotics']`, target `None`, max_hops 3. Resolved question: "Could new export controls hit Solstice's supply chain?"

```text
(rule-based answer)
Delta Servo Corp is a supplier to Solstice Robotics [PROFILE, a10].
The text of alert a10 does not name Solstice Robotics; this link rests on the entity annotation and the client profile [PROFILE, a10].
a10 (2026-07-24): "Delta Servo Corp, a servo motor supplier to industrial automation OEMs, opened a new manufacturing plant in South Korea to meet growing demand" [a10].
Delta Servo Corp has a presence in South Korea [a10].
US Department of Commerce is reported as affecting South Korea [a13].
a13 (2026-08-04): "The US Department of Commerce proposed new export control rules targeting advanced robotics and AI-enabled components, citing national security concerns" [a13].
```

*Gate:* `answerable` · *method:* `template` · *citations:* PROFILE, a10, a13

<details><summary>Graph paths used</summary>

1. score 0.332
   - `Solstice Robotics -HAS_SUPPLIER-> Delta Servo Corp  [PROFILE, a10(annotation)] (confirmed)`
   - `Delta Servo Corp -PRESENT_IN-> South Korea  [a10(co_mention)] (discovered)`
   - `US Department of Commerce -AFFECTS-> South Korea  [a13(co_mention)] (discovered)`

</details>

## Q6. Who is Solstice's CEO?

*Plan:* intent `NEIGHBORHOOD`, entities `['company:solstice-robotics']`, target `CEO`, max_hops 2. Resolved question: "Who is Solstice's CEO?"

```text
(rule-based answer)
Not found: no evidence on "CEO" for Solstice Robotics in the alerts or client profile.
Closest related evidence: a02 (2026-08-10): "Solstice Robotics named Elena Marsh as Chief Financial Officer, effective September 1" [a02].
```

*Gate:* `partial` · *method:* `template` · *citations:* a02
