# Connie-Lite demo transcript

Provider: `anthropic`, model `claude-haiku-4-5`

## Q1. Which of Solstice's suppliers carry commodity risk, and which commodity?

*Plan:* intent `SUPPLIER_RISK`, entities `['company:solstice-robotics']`, target `None`, max_hops 2. Resolved question: "Which of Solstice Robotics' suppliers carry commodity risk, and which commodity?"

```text
Solstice Robotics has one identified supplier carrying commodity risk: Ferrotech Alloys is exposed to rare earth magnets [a09]. The alert text itself does not name Solstice Robotics, though Ferrotech Alloys is confirmed as a supplier of Solstice Robotics [PROFILE, a09]. Rare earth magnet prices have risen nearly 40% year-over-year due to export restrictions, creating cost pressure for robotics manufacturers [a09].
```

*Gate:* `answerable` · *method:* `llm` · *citations:* a09, PROFILE

<details><summary>Graph paths used</summary>

1. score 0.528
   - `Solstice Robotics -HAS_SUPPLIER-> Ferrotech Alloys  [PROFILE, a09(annotation)] (confirmed)`
   - `Ferrotech Alloys -EXPOSED_TO-> rare earth magnets  [a09(co_mention)] (discovered)`

</details>

## Q2. And what about their exposure to tariffs?

*Plan:* intent `CONNECT`, entities `['company:ferrotech-alloys']`, target `tariffs`, max_hops 2. Resolved question: "What is Ferrotech Alloys' exposure to tariffs?"

```text
Not found: Information about Ferrotech Alloys' exposure to tariffs is not in the evidence. The available alert discusses rare earth magnet price increases due to export restrictions rather than tariffs [a09].
```

*Gate:* `partial` · *method:* `llm` · *citations:* a09

## Q3. Are any of Solstice's competitors pushing into the same end markets as its customers?

*Plan:* intent `SHARED_MARKET`, entities `['company:solstice-robotics']`, target `None`, max_hops 2. Resolved question: "Are any of Solstice Robotics' competitors pushing into the same end markets as its customers?"

```text
Yes, Solstice Robotics' competitors are pushing into the same end markets as its customers [a05, a06, a11]. Kestrel Automation, a competitor, operates in warehouse automation [a05], the same market as Solstice customers Northline Logistics, Bayview Fulfillment, and newly discovered, not in the client profile Orion Freight Systems [a04, a12, a22]. Similarly, ArcWorks Robotics competes in automotive manufacturing [a06], where customer Meridian Auto Group is making a significant $2 billion automation investment [a11]. The alert text itself does not name Solstice Robotics in the Kestrel Automation and ArcWorks Robotics announcements [a05, a06, a28].
```

*Gate:* `answerable` · *method:* `llm` · *citations:* a05, a06, a11, a04, a12, a22, a28

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

*Plan:* intent `DISCOVERED`, entities `['company:solstice-robotics']`, target `None`, max_hops 2. Resolved question: "Does Solstice Robotics have any supplier or customer relationships that aren't in its profile?"

```text
Yes, Solstice Robotics has two newly discovered supplier and customer relationships not in its client profile [a21, a22]. The company has a newly discovered, not in the client profile supplier relationship with Hanley Precision Casting, a Vietnam-based components maker for structural robot housings [a21]. Additionally, Solstice Robotics has a newly discovered, not in the client profile customer relationship with Orion Freight Systems, a logistics operator that has deployed Solstice Robotics picking arms across three regional distribution hubs [a22].
```

*Gate:* `answerable` · *method:* `llm` · *citations:* a21, a22

<details><summary>Graph paths used</summary>

1. score 0.840
   - `Solstice Robotics -HAS_SUPPLIER-> Hanley Precision Casting  [a21(text)] (discovered)`
2. score 0.740
   - `Solstice Robotics -HAS_CUSTOMER-> Orion Freight Systems  [a22(text)] (discovered)`

</details>

## Q5. Could new export controls hit Solstice's supply chain?

*Plan:* intent `SUPPLIER_RISK`, entities `['company:solstice-robotics']`, target `export controls`, max_hops 3. Resolved question: "Could new export controls hit Solstice Robotics' supply chain?"

```text
Yes, new export controls could impact Solstice Robotics' supply chain [a13]. Solstice Robotics relies on Delta Servo Corp as a supplier [PROFILE], though the alert text itself does not name the client [a10]. Delta Servo Corp recently opened a manufacturing plant in South Korea [a10], and the US Department of Commerce has proposed new export control rules targeting advanced robotics components, with industry groups specifically warning these rules could disrupt supply chains for domestic manufacturers sourcing from South Korea [a13].
```

*Gate:* `answerable` · *method:* `llm` · *citations:* a13, PROFILE, a10

<details><summary>Graph paths used</summary>

1. score 0.332
   - `Solstice Robotics -HAS_SUPPLIER-> Delta Servo Corp  [PROFILE, a10(annotation)] (confirmed)`
   - `Delta Servo Corp -PRESENT_IN-> South Korea  [a10(co_mention)] (discovered)`
   - `US Department of Commerce -AFFECTS-> South Korea  [a13(co_mention)] (discovered)`

</details>

## Q6. Who is Solstice's CEO?

*Plan:* intent `NEIGHBORHOOD`, entities `['company:solstice-robotics']`, target `CEO`, max_hops 2. Resolved question: "Who is Solstice Robotics' CEO?"

```text
Not found: The CEO of Solstice Robotics is not identified in the available evidence. The evidence includes information about Solstice Robotics' new CFO, Elena Marsh [a02], and a management presentation at an investor conference [a27], but does not specify who serves as CEO.
```

*Gate:* `partial` · *method:* `llm` · *citations:* a02, a27
