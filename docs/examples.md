# Examples (generated from data/sample_awr_export.csv)

All output below is real program output. The sample data is fictional (`.example` domains): our site is `shoeshop.example`, competitors are `runfast.example` and `sportzone.example`. There are three AWR ranking updates (2026-10-05, 10-12, 10-19) and four keyword groups.

## 1. Import AWR data as FOL facts (latest update vs. the one before)

```
$ python -m seo_planner import data/sample_awr_export.csv --site shoeshop.example --out knowledge_base/facts_sample.fol
{
  "keywords": 11,
  "competitors": [
    "runfast.example",
    "sportzone.example"
  ],
  "site": "shoeshop.example",
  "engine": "Google USA",
  "engines_available": [
    "Google USA"
  ],
  "current_date": "2026-10-19",
  "previous_date": "2026-10-12",
  "groups": [
    "Accessories",
    "Deals",
    "Running Shoes",
    "Sneakers"
  ]
}
Wrote 72 facts to knowledge_base/facts_sample.fol
```

## 2. Query answering

### Which keywords need work, and with what priority?

```
$ python -m seo_planner query knowledge_base/facts_sample.fol "Priority(K, P)"
K = 'best running shoes', P = 2
K = 'cheap running shoes', P = 3
K = 'marathon shoes', P = 2
K = 'running shoes online', P = 3
K = 'running shoes sale', P = 3
K = 'sneaker cleaning kit', P = 2
K = 'trail running shoes', P = 1
K = 'waterproof sneakers', P = 2
K = 'womens running shoes', P = 1
(9 answers)
```

### Which keywords are on page one but still beaten by a competitor?

```
$ python -m seo_planner query knowledge_base/facts_sample.fol "FirstPage(K), BeatenBy(K, C), CompetitorRanking(K, C, Q)"
C = 'runfast.example', K = 'waterproof sneakers', Q = 3
C = 'runfast.example', K = 'womens running shoes', Q = 5
C = 'sportzone.example', K = 'womens running shoes', Q = 4
(3 answers)
```

### Which keywords dropped, and by how much? (arithmetic in queries)

```
$ python -m seo_planner query knowledge_base/facts_sample.fol "Dropped(K), Ranking(K, P), PreviousRanking(K, P0), D is P - P0"
D = 7, K = 'womens running shoes', P = 9, P0 = 2
D = 9, K = 'trail running shoes', P = 14, P0 = 5
(2 answers)
```

### Which keyword groups contain urgent keywords?

```
$ python -m seo_planner query knowledge_base/facts_sample.fol "InGroup(K, G), Urgent(K)"
G = 'Running Shoes', K = 'trail running shoes'
G = 'Running Shoes', K = 'womens running shoes'
(2 answers)
```

### Why does 'trail running shoes' have priority 1? (proof tree)

```
$ python -m seo_planner query knowledge_base/facts_sample.fol "Priority('trail running shoes', P)" --why
P = 1
  Priority('trail running shoes', 1)   [rule: Priority(K, 1) :- Urgent(K).]
    Urgent('trail running shoes')   [rule: Urgent(K) :- NeedsOptimization(K), Dropped(K).]
      NeedsOptimization('trail running shoes')   [rule: NeedsOptimization(K) :- Ranking(K, P), P > 10.]
        Ranking('trail running shoes', 14)   [fact]
        14 > 10   [built-in]
      Dropped('trail running shoes')   [rule: Dropped(K) :- Ranking(K, P), PreviousRanking(K, P0), D is P - P0, D >= 5.]
        Ranking('trail running shoes', 14)   [fact]
        PreviousRanking('trail running shoes', 5)   [fact]
        9 is 14 - 5   [built-in]
        9 >= 5   [built-in]

(1 answer)
```

## 3. Plan for the five most urgent keywords (A*, strict priority)

```
$ python -m seo_planner plan knowledge_base/facts_sample.fol
Keywords in scope (5), most urgent first:
  - trail running shoes
  - womens running shoes
  - best running shoes
  - marathon shoes
  - sneaker cleaning kit

A*: plan with 26 steps, total cost 45, 26 nodes expanded, 0.26s

  1. [1] Audit the ranking page and SERP for 'trail running shoes' [#14, priority 1, page https://shoeshop.example/trail-running-shoes]
        AuditPage('trail running shoes')  because InScope('trail running shoes'), not Audited('trail running shoes'), not Blocked('trail running shoes')
  2. [2] Investigate why 'trail running shoes' dropped (indexing, cannibalisation, SERP changes) [#5 -> #14]
        InvestigateDrop('trail running shoes')  because Audited('trail running shoes'), Dropped('trail running shoes'), not DropInvestigated('trail running shoes')
  3. [2] Analyse competitor pages outranking us for 'trail running shoes' [we are #14; ahead of us: runfast.example #6, sportzone.example #11]
        AnalyzeCompetitors('trail running shoes')  because Audited('trail running shoes'), LosingToCompetitor('trail running shoes'), not CompetitorsAnalyzed('trail running shoes')
  4. [4] Add the topics competitors cover that our page misses for 'trail running shoes'
        CloseContentGap('trail running shoes')  because CompetitorsAnalyzed('trail running shoes'), RankingPageExists('trail running shoes'), not ContentImproved('trail running shoes')
  5. [1] Add internal links pointing to the page for 'trail running shoes'
        AddInternalLinks('trail running shoes')  because Improved('trail running shoes'), not InternalLinksAdded('trail running shoes')
  6. [1] Audit the ranking page and SERP for 'womens running shoes' [#9, priority 1, page https://shoeshop.example/womens-running-shoes]
        AuditPage('womens running shoes')  because InScope('womens running shoes'), not Audited('womens running shoes'), not Blocked('womens running shoes')
  7. [2] Investigate why 'womens running shoes' dropped (indexing, cannibalisation, SERP changes) [#2 -> #9]
        InvestigateDrop('womens running shoes')  because Audited('womens running shoes'), Dropped('womens running shoes'), not DropInvestigated('womens running shoes')
  8. [2] Analyse competitor pages outranking us for 'womens running shoes' [we are #9; ahead of us: sportzone.example #4, runfast.example #5]
        AnalyzeCompetitors('womens running shoes')  because Audited('womens running shoes'), LosingToCompetitor('womens running shoes'), not CompetitorsAnalyzed('womens running shoes')
  9. [4] Add the topics competitors cover that our page misses for 'womens running shoes'
        CloseContentGap('womens running shoes')  because CompetitorsAnalyzed('womens running shoes'), RankingPageExists('womens running shoes'), not ContentImproved('womens running shoes')
 10. [1] Add internal links pointing to the page for 'womens running shoes'
        AddInternalLinks('womens running shoes')  because Improved('womens running shoes'), not InternalLinksAdded('womens running shoes')
 11. [1] Audit the ranking page and SERP for 'best running shoes' [#12, priority 2, page https://shoeshop.example/best-running-shoes]
        AuditPage('best running shoes')  because InScope('best running shoes'), not Audited('best running shoes'), not Blocked('best running shoes')
 12. [2] Analyse competitor pages outranking us for 'best running shoes' [we are #12; ahead of us: runfast.example #4, sportzone.example #9]
        AnalyzeCompetitors('best running shoes')  because Audited('best running shoes'), LosingToCompetitor('best running shoes'), not CompetitorsAnalyzed('best running shoes')
 13. [4] Add the topics competitors cover that our page misses for 'best running shoes'
        CloseContentGap('best running shoes')  because CompetitorsAnalyzed('best running shoes'), RankingPageExists('best running shoes'), not ContentImproved('best running shoes')
 14. [1] Add internal links pointing to the page for 'best running shoes'
        AddInternalLinks('best running shoes')  because Improved('best running shoes'), not InternalLinksAdded('best running shoes')
 15. [1] Audit the ranking page and SERP for 'marathon shoes' [#17, priority 2, page https://shoeshop.example/marathon-shoes]
        AuditPage('marathon shoes')  because InScope('marathon shoes'), not Audited('marathon shoes'), not Blocked('marathon shoes')
 16. [2] Optimise title, meta description and headings for 'marathon shoes'
        OptimizeOnPage('marathon shoes')  because Audited('marathon shoes'), StrikingDistance('marathon shoes'), not OnPageOptimized('marathon shoes')
 17. [1] Add internal links pointing to the page for 'marathon shoes'
        AddInternalLinks('marathon shoes')  because Improved('marathon shoes'), not InternalLinksAdded('marathon shoes')
 18. [1] Audit the ranking page and SERP for 'sneaker cleaning kit' [#19, priority 2, page https://shoeshop.example/cleaning-kit]
        AuditPage('sneaker cleaning kit')  because InScope('sneaker cleaning kit'), not Audited('sneaker cleaning kit'), not Blocked('sneaker cleaning kit')
 19. [2] Analyse competitor pages outranking us for 'sneaker cleaning kit' [we are #19; ahead of us: sportzone.example #6]
        AnalyzeCompetitors('sneaker cleaning kit')  because Audited('sneaker cleaning kit'), LosingToCompetitor('sneaker cleaning kit'), not CompetitorsAnalyzed('sneaker cleaning kit')
 20. [4] Add the topics competitors cover that our page misses for 'sneaker cleaning kit'
        CloseContentGap('sneaker cleaning kit')  because CompetitorsAnalyzed('sneaker cleaning kit'), RankingPageExists('sneaker cleaning kit'), not ContentImproved('sneaker cleaning kit')
 21. [1] Add internal links pointing to the page for 'sneaker cleaning kit'
        AddInternalLinks('sneaker cleaning kit')  because Improved('sneaker cleaning kit'), not InternalLinksAdded('sneaker cleaning kit')
 22. [1] Schedule an AWR ranking update to measure the effect on 'best running shoes'
        ScheduleRecheck('best running shoes')  because Addressed('best running shoes'), not Rechecked('best running shoes')
 23. [1] Schedule an AWR ranking update to measure the effect on 'marathon shoes'
        ScheduleRecheck('marathon shoes')  because Addressed('marathon shoes'), not Rechecked('marathon shoes')
 24. [1] Schedule an AWR ranking update to measure the effect on 'sneaker cleaning kit'
        ScheduleRecheck('sneaker cleaning kit')  because Addressed('sneaker cleaning kit'), not Rechecked('sneaker cleaning kit')
 25. [1] Schedule an AWR ranking update to measure the effect on 'trail running shoes'
        ScheduleRecheck('trail running shoes')  because Addressed('trail running shoes'), not Rechecked('trail running shoes')
 26. [1] Schedule an AWR ranking update to measure the effect on 'womens running shoes'
        ScheduleRecheck('womens running shoes')  because Addressed('womens running shoes'), not Rechecked('womens running shoes')
```

## 4. Plan for one keyword group

```
$ python -m seo_planner plan knowledge_base/facts_sample.fol --group Accessories --compare
Keywords in scope (1), most urgent first:
  - sneaker cleaning kit

A*: plan with 5 steps, total cost 9, 5 nodes expanded, 0.01s

  1. [1] Audit the ranking page and SERP for 'sneaker cleaning kit' [#19, priority 2, page https://shoeshop.example/cleaning-kit]
        AuditPage('sneaker cleaning kit')  because InScope('sneaker cleaning kit'), not Audited('sneaker cleaning kit'), not Blocked('sneaker cleaning kit')
  2. [2] Analyse competitor pages outranking us for 'sneaker cleaning kit' [we are #19; ahead of us: sportzone.example #6]
        AnalyzeCompetitors('sneaker cleaning kit')  because Audited('sneaker cleaning kit'), LosingToCompetitor('sneaker cleaning kit'), not CompetitorsAnalyzed('sneaker cleaning kit')
  3. [4] Add the topics competitors cover that our page misses for 'sneaker cleaning kit'
        CloseContentGap('sneaker cleaning kit')  because CompetitorsAnalyzed('sneaker cleaning kit'), RankingPageExists('sneaker cleaning kit'), not ContentImproved('sneaker cleaning kit')
  4. [1] Add internal links pointing to the page for 'sneaker cleaning kit'
        AddInternalLinks('sneaker cleaning kit')  because Improved('sneaker cleaning kit'), not InternalLinksAdded('sneaker cleaning kit')
  5. [1] Schedule an AWR ranking update to measure the effect on 'sneaker cleaning kit'
        ScheduleRecheck('sneaker cleaning kit')  because Addressed('sneaker cleaning kit'), not Rechecked('sneaker cleaning kit')

Algorithm comparison
  algorithm found   steps  cost  expanded  generated     time
  BFS       True        4    11         8         20    0.01s  
  UCS       True        5     9        11         23    0.01s  
  A*        True        5     9         5         12    0.01s  
```

## 5. BFS vs. UCS/A*: fewest steps is not cheapest

```
$ python -m seo_planner plan knowledge_base/facts_sample.fol --keyword "running shoes sale" --algorithm bfs
Keywords in scope (1), most urgent first:
  - running shoes sale

BFS: plan with 3 steps, total cost 9, 4 nodes expanded, 0.00s

  1. [1] Audit the ranking page and SERP for 'running shoes sale' [#33, priority 3, page https://shoeshop.example/sale]
        AuditPage('running shoes sale')  because InScope('running shoes sale'), not Audited('running shoes sale'), not Blocked('running shoes sale')
  2. [7] Publish a supporting article on 'running shoes sale' that covers missing topics and links to the page
        PublishSupportingArticle('running shoes sale')  because Audited('running shoes sale'), RankingPageExists('running shoes sale'), not ContentImproved('running shoes sale'), not InternalLinksAdded('running shoes sale')
  3. [1] Schedule an AWR ranking update to measure the effect on 'running shoes sale'
        ScheduleRecheck('running shoes sale')  because Addressed('running shoes sale'), not Rechecked('running shoes sale')
```

```
$ python -m seo_planner plan knowledge_base/facts_sample.fol --keyword "running shoes sale" --algorithm astar
Keywords in scope (1), most urgent first:
  - running shoes sale

A*: plan with 4 steps, total cost 8, 4 nodes expanded, 0.00s

  1. [1] Audit the ranking page and SERP for 'running shoes sale' [#33, priority 3, page https://shoeshop.example/sale]
        AuditPage('running shoes sale')  because InScope('running shoes sale'), not Audited('running shoes sale'), not Blocked('running shoes sale')
  2. [5] Rewrite and expand the content targeting 'running shoes sale'
        RewriteContent('running shoes sale')  because Audited('running shoes sale'), RankingPageExists('running shoes sale'), not StrikingDistance('running shoes sale'), not NotRanking('running shoes sale'), not ContentImproved('running shoes sale')
  3. [1] Add internal links pointing to the page for 'running shoes sale'
        AddInternalLinks('running shoes sale')  because Improved('running shoes sale'), not InternalLinksAdded('running shoes sale')
  4. [1] Schedule an AWR ranking update to measure the effect on 'running shoes sale'
        ScheduleRecheck('running shoes sale')  because Addressed('running shoes sale'), not Rechecked('running shoes sale')
```

## 6. Keyword with no ranking page: landing page before content work

```
$ python -m seo_planner plan knowledge_base/facts_sample.fol --keyword "cheap running shoes"
Keywords in scope (1), most urgent first:
  - cheap running shoes

A*: plan with 6 steps, total cost 17, 6 nodes expanded, 0.01s

  1. [1] Audit the ranking page and SERP for 'cheap running shoes' [not ranking, priority 3, no ranking page]
        AuditPage('cheap running shoes')  because InScope('cheap running shoes'), not Audited('cheap running shoes'), not Blocked('cheap running shoes')
  2. [8] Create a dedicated landing page for 'cheap running shoes'
        CreateLandingPage('cheap running shoes')  because Audited('cheap running shoes'), NotRanking('cheap running shoes'), not HasLandingPage('cheap running shoes')
  3. [2] Analyse competitor pages outranking us for 'cheap running shoes' [we are not ranking; ahead of us: runfast.example #12, sportzone.example #20]
        AnalyzeCompetitors('cheap running shoes')  because Audited('cheap running shoes'), LosingToCompetitor('cheap running shoes'), not CompetitorsAnalyzed('cheap running shoes')
  4. [4] Add the topics competitors cover that our page misses for 'cheap running shoes'
        CloseContentGap('cheap running shoes')  because CompetitorsAnalyzed('cheap running shoes'), RankingPageExists('cheap running shoes'), not ContentImproved('cheap running shoes')
  5. [1] Add internal links pointing to the page for 'cheap running shoes'
        AddInternalLinks('cheap running shoes')  because Improved('cheap running shoes'), not InternalLinksAdded('cheap running shoes')
  6. [1] Schedule an AWR ranking update to measure the effect on 'cheap running shoes'
        ScheduleRecheck('cheap running shoes')  because Addressed('cheap running shoes'), not Rechecked('cheap running shoes')
```

## 7. Algorithm comparison without the priority policy (larger state space)

```
$ python -m seo_planner plan knowledge_base/facts_sample.fol --top 3 --no-strict-priority --compare
Keywords in scope (3), most urgent first:
  - trail running shoes
  - womens running shoes
  - best running shoes

A*: plan with 17 steps, total cost 31, 17 nodes expanded, 0.12s

  1. [1] Audit the ranking page and SERP for 'best running shoes' [#12, priority 2, page https://shoeshop.example/best-running-shoes]
        AuditPage('best running shoes')  because InScope('best running shoes'), not Audited('best running shoes')
  2. [2] Analyse competitor pages outranking us for 'best running shoes' [we are #12; ahead of us: runfast.example #4, sportzone.example #9]
        AnalyzeCompetitors('best running shoes')  because Audited('best running shoes'), LosingToCompetitor('best running shoes'), not CompetitorsAnalyzed('best running shoes')
  3. [4] Add the topics competitors cover that our page misses for 'best running shoes'
        CloseContentGap('best running shoes')  because CompetitorsAnalyzed('best running shoes'), RankingPageExists('best running shoes'), not ContentImproved('best running shoes')
  4. [1] Audit the ranking page and SERP for 'trail running shoes' [#14, priority 1, page https://shoeshop.example/trail-running-shoes]
        AuditPage('trail running shoes')  because InScope('trail running shoes'), not Audited('trail running shoes')
  5. [2] Investigate why 'trail running shoes' dropped (indexing, cannibalisation, SERP changes) [#5 -> #14]
        InvestigateDrop('trail running shoes')  because Audited('trail running shoes'), Dropped('trail running shoes'), not DropInvestigated('trail running shoes')
  6. [2] Analyse competitor pages outranking us for 'trail running shoes' [we are #14; ahead of us: runfast.example #6, sportzone.example #11]
        AnalyzeCompetitors('trail running shoes')  because Audited('trail running shoes'), LosingToCompetitor('trail running shoes'), not CompetitorsAnalyzed('trail running shoes')
  7. [4] Add the topics competitors cover that our page misses for 'trail running shoes'
        CloseContentGap('trail running shoes')  because CompetitorsAnalyzed('trail running shoes'), RankingPageExists('trail running shoes'), not ContentImproved('trail running shoes')
  8. [1] Audit the ranking page and SERP for 'womens running shoes' [#9, priority 1, page https://shoeshop.example/womens-running-shoes]
        AuditPage('womens running shoes')  because InScope('womens running shoes'), not Audited('womens running shoes')
  9. [2] Investigate why 'womens running shoes' dropped (indexing, cannibalisation, SERP changes) [#2 -> #9]
        InvestigateDrop('womens running shoes')  because Audited('womens running shoes'), Dropped('womens running shoes'), not DropInvestigated('womens running shoes')
 10. [2] Analyse competitor pages outranking us for 'womens running shoes' [we are #9; ahead of us: sportzone.example #4, runfast.example #5]
        AnalyzeCompetitors('womens running shoes')  because Audited('womens running shoes'), LosingToCompetitor('womens running shoes'), not CompetitorsAnalyzed('womens running shoes')
 11. [4] Add the topics competitors cover that our page misses for 'womens running shoes'
        CloseContentGap('womens running shoes')  because CompetitorsAnalyzed('womens running shoes'), RankingPageExists('womens running shoes'), not ContentImproved('womens running shoes')
 12. [1] Add internal links pointing to the page for 'best running shoes'
        AddInternalLinks('best running shoes')  because Improved('best running shoes'), not InternalLinksAdded('best running shoes')
 13. [1] Add internal links pointing to the page for 'trail running shoes'
        AddInternalLinks('trail running shoes')  because Improved('trail running shoes'), not InternalLinksAdded('trail running shoes')
 14. [1] Add internal links pointing to the page for 'womens running shoes'
        AddInternalLinks('womens running shoes')  because Improved('womens running shoes'), not InternalLinksAdded('womens running shoes')
 15. [1] Schedule an AWR ranking update to measure the effect on 'best running shoes'
        ScheduleRecheck('best running shoes')  because Addressed('best running shoes'), not Rechecked('best running shoes')
 16. [1] Schedule an AWR ranking update to measure the effect on 'trail running shoes'
        ScheduleRecheck('trail running shoes')  because Addressed('trail running shoes'), not Rechecked('trail running shoes')
 17. [1] Schedule an AWR ranking update to measure the effect on 'womens running shoes'
        ScheduleRecheck('womens running shoes')  because Addressed('womens running shoes'), not Rechecked('womens running shoes')

Algorithm comparison
  algorithm found   steps  cost  expanded  generated     time
  BFS       True       14    37     10154      62838   17.12s  
  UCS       True       17    31     10655      64450   18.06s  
  A*        True       17    31        17         97    0.12s  
```
