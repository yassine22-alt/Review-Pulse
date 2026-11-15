# Demand analysis: what requirements ask to be measured

Source: all.csv. Sentences: 862. Method: deterministic quantity parser and keyword table, no model.

- with at least one numeric quantity: 172 (20%)
- count-style requirement without units: 41 (5%)
- no quantity found (qualitative or beyond this parser): 649 (75%)

## What is asked, and can we measure it?

| Quantity of | Sentences | Plan reader today |
|---|---|---|
| number of storeys / occupants / items | 56 | partial |
| width / clear opening | 26 | measured |
| unclassified | 22 | unclassified |
| stair geometry | 20 | partial |
| headroom / height | 16 | needs section or schedule |
| floor area | 11 | measured |
| structural load | 11 | needs calculation or structural drawings |
| thermal / energy | 10 | needs specification or calculation |
| lighting / daylight | 10 | needs calculation (glazing ratio is partly derivable) |
| slope / gradient | 10 | plan, not measured yet |
| fire resistance | 8 | needs specification or schedule |
| ventilation / air | 8 | needs specification or calculation |
| distance / travel | 8 | partial |
| depth / thickness / diameter / length | 5 | plan, not measured yet |

## Requirements without a number: what they ask for

| Kind | Sentences | Could a plan graph answer it? |
|---|---|---|
| other | 239 | unknown |
| access, route or connection | 156 | often, as a presence, route or relation check |
| provision / presence | 146 | often, as a presence, route or relation check |
| quality or judgement | 62 | needs a person's judgement |
| prohibition | 32 | often, as a presence, route or relation check |
| reference to another document or clause | 14 | points elsewhere |

## Supply summary (counts quantity groups, a sentence can appear in several)

| Status | Groups |
|---|---|
| partial | 84 |
| measured | 37 |
| unclassified | 22 |
| needs specification or calculation | 18 |
| needs section or schedule | 16 |
| plan, not measured yet | 15 |
| needs calculation or structural drawings | 11 |
| needs calculation (glazing ratio is partly derivable) | 10 |
| needs specification or schedule | 8 |

Share of requested quantities that are measured today: 17%; measured or partly: 55%.

## Units seen

- mm: 106
- m: 37
- m2: 15
- %: 11
- ratio: 8
- W: 6
- Cel: 5
- kN: 4
- L: 4
- kN/m2: 3
- W/m2K: 3
- s: 2
- m3: 2
- mg: 2
- ppm: 2
- kPa: 2
- kg: 2
- min: 2
- kW: 2
- MJ: 1
- lx: 1
- K: 1
- deg: 1
- l/s: 1
- in: 1
- Pa: 1
- pm: 1

## Examples

**floor area**
- In a building consisting primarily of one storey, no more than 200 m2 of fire-compartmented and no more than 50 m2 of non-fire-compartmented areas that essentially relate to the business of the buildi
- Attics and uppermost floor voids shall be divided into 400 m2 parts.

**stair geometry**
- The landing in front of the outside door shall be at least 1,500 millimetres wide and at least 1,500 millimetres long.
- A  building  with  dwellings  or  accommodation  or  patient  rooms  shall  be  designed  and implemented so that the reverberation time of the staircase and exit route is no more than 1.3 seconds.

**width / clear opening**
- The landing in front of the outside door shall be at least 1,500 millimetres wide and at least 1,500 millimetres long.
- in residential buildings of not more than two storeys, one exit of no less than 900 millimetres in width is permitted.

**structural load**
- Storage premises with a fire load exceeding 1,200 MJ/m2 are not permitted within the building.
- If the internal ties must be centred on the supporting line, the minimum value of the tie force, 10 kN, will also be applied to internal ties.

**depth / thickness / diameter / length**
- A dwelling that is intended for service housing or supported housing of a person with mobility and functional impairment shall, irrespective of the number of storeys in the building, have a turning  s
- A  dwelling  that  is  intended  for  sheltered  housing  or  supported  housing  of  a  person  with mobility or functional impairment shall have at least one toilet and washing facility which has a 

**unclassified**
- The toilet seat shall be placed between 200 and 300 millimetres from the rear wall.
- Large  roof  surfaces  must  be  divided  into  parts  of  no  more  than  2,400 square  metres.

**headroom / height**
- If the height of the building does not exceed 28 metres, access to the attic fire compartments from the outside shall be required.
- In a new building, the crawl space height must be 0.8 metres on average at the minimum.

**fire resistance**
- The fire performance of the external wall structure of a building no more than 56 metres in height may also be demonstrated by a fullscale test.
- Parapets in categories A to E and panel parts of walls acting as parapets, as well as their fasteners, shall be designed to the concentrated load Qk = 0.3 kN acting on a random spot.

**thermal / energy**
- When calculating the reference heat loss of a building, the value of 2.0 m3/(h m2) shall be used as the reference value for the air leakage rate figure for the building envelope.
- An upstand built on site should not exceed a U-value of 0.35W/(m2K).

**number of storeys / occupants / items**
- At least 30% of the ties shall be located in the immediate vicinity of the grid lines of the columns and the walls.
- For large roofs, where the smaller horizontal dimension of the roof is 50 m or more, and the topography is windswept, the value of the exposure coefficient shall be at least 1.

**lighting / daylight**
- The free height from the ground or from the surface of a driveway or walkway of the lower edge of a structural element, device or equipment protruding from the building, such as a balcony, bay window,
- If performance requires thicker glass to be used, an equivalent window unit with standard thickness (6mm) glazing should be shown to meet the required standard.

**slope / gradient**
- The slope of the floor surface in the seating area and access route may not exceed 8 per cent (1:12.5).
- A roof with a pitch greater than 1:8 must be constructed making appropriate use of walkways, roof ladders, safety ladders, roof stairs, roof treads and foot rails.

**ventilation / air**
- The air flows shall be designed so that the average carbon monoxide concentration in a parking garage for motor vehicles during the hour of use assessed as the most critical does not exceed 35 mg/m3 (
- Air flows in the continuous working area of a parking garage for motor vehicles shall be designed so that the instantaneous carbon monoxide concentration does not exceed 7 mg/m3 (6 ppm).

**distance / travel**
- A building shall be provided with a permanently installed dry riser that is suitable for its purpose for transporting water for fire extinguishing: 1) in the premises above the entry level of the buil
- The water temperature of the water in the hot water system shall be at least 55 degrees Celsius and available from the hot water plumbing fixture within 20 seconds.

## Caveats

- Keyword classification is crude: it can mislabel a quantity. Use the table for ranking, not for exact counts.
- The corpus is England and Finland building regulations in English; it says nothing about other subjects or languages.
- Sentences were chosen by the corpus authors as self-contained rules, so qualitative clauses are under-represented.
