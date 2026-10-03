# Concordia product charter

Status: **LOCKED FOR IMPLEMENTATION**

## Identity

- Product: **Concordia**
- Tagline: **Different Teams. Same Truth.**
- Secondary line: **Ask naturally. Resolve consistently.**
- Fictional manufacturer: **Meridian Motion**
- Product category: governed supply-chain semantic and conversational analytics

The name is suitable for a hackathon identity. It has not received legal or
trademark clearance for commercial use.

## Problem statement

Supply-chain data is fragmented across ERP, logistics, supplier, manufacturing,
inventory, and customer systems. Teams implement different joins, filters, time
windows, and definitions, so identical business questions produce conflicting
answers.

Concordia must:

1. define core entities, relationships, hierarchies, and canonical metrics;
2. encode those definitions as governed semantic views;
3. answer natural-language questions through those definitions;
4. prove that planning, procurement, and logistics resolve the same metric
   identically for the same scope.

Judging priorities are real-world relevance, technical execution, and solution
completeness.

## Product thesis

The scarce capability is not another dashboard or classifier. It is a
machine-enforced agreement about:

- what an entity means;
- which events establish a business fact;
- which date and quantity count;
- which rows are included or excluded;
- how late-arriving records restate an answer;
- and which definition the conversational layer is allowed to use.

The metric contract, not the language model, is the source of truth.

## Data decision

Use one coherent simulated manufacturer rather than unrelated public datasets.
The simulator represents what can happen in a real supply chain:

- partial receipts and deliveries;
- regional and locality-specific delays;
- failed and misdirected delivery attempts;
- quality holds, scrap, returns, complaints, and ratings;
- promise revisions;
- BOM and supplier-price effectivity;
- late invoices and restatements;
- identity, unit, currency, and timezone conflicts.

The simulation is valid evidence of deterministic semantic consistency. It is
not valid evidence of market frequency, causal laws, model quality, or business
improvement.

## Audience

Primary:

- VP/Head of Supply Chain;
- supply planner;
- procurement manager;
- logistics/customer-delivery manager.

Secondary:

- data steward;
- enterprise data/IT reviewer;
- internal auditor;
- hackathon technical judge.

## UX decision

Build one application with progressive disclosure.

Business users see direct answers, material impact, evidence, and definitions in
plain language. Reviewers can open governance and audit details in context.
There is no separate engineering application because that would create a second
experience and encourage duplicated metric logic.

## Canonical claims

Concordia may claim:

- the simulated source systems are causally coherent;
- the source representations are deliberately inconsistent;
- the semantic layer deterministically resolves the published contracts;
- same-scope persona answers are identical;
- answers carry evidence, scope, version, freshness, and exclusions;
- unsupported or unresolved questions abstain.

Concordia may not claim:

- real customer or supplier results;
- measured cost savings or service improvement;
- industry-average performance;
- predictive accuracy;
- causation outside the simulator's declared event chain;
- successful deployment against a real ERP estate;
- zero hallucination.

## Definition of done

The product is complete when:

1. the five metric contracts are versioned and tested;
2. the full entity chain is represented and traceable;
3. the same benchmark question returns identical exact metric fields and
   evidence hash for planning, procurement, and logistics under equal
   entitlement;
4. late data can be replayed at two as-of times;
5. evidence and exclusions explain every headline number;
6. ambiguous OTD questions are clarified;
7. the LLM cannot bypass governed objects;
8. local and deployed demonstrations show the permanent simulation disclosure;
9. all golden, metamorphic, provenance, and access-control tests pass;
10. the five-minute demo can be completed without hidden setup.

## Kill criteria

Stop or reduce scope if any of these becomes necessary:

- a metric formula exists in Streamlit or prompt text as well as SQL;
- the product must call synthetic records observed;
- the hero answer depends on an unrestricted generated query;
- an unresolved unit or identity is silently guessed;
- the app needs a second dashboard to explain the first;
- a predictive model is added only to appear advanced;
- the trace cannot be reconciled to exact event and document identifiers.

