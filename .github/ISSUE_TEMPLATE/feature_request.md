---
name: Feature request
about: A control or change that would catch a fault this library currently misses
title: "[feature] "
labels: enhancement
---

<!--
Read this first: this project refuses controls it has no evidence for. "A control nobody
has needed yet is a liability with a maintenance cost." A request from a real pipeline,
with the fault that motivated it, is the one that gets built.
-->

## The problem

<!-- What actually went wrong, or could. Be concrete: which pipeline, which write, what
     the dashboard said while the data was wrong. -->

## The proposed control or change

<!-- What it would check, when it would run (write boundary? nightly? around a repair?),
     and what it would be allowed to do - raise, or warn only. -->

## What fault would this catch, and how would we prove it fires on that fault?

<!-- This is the question this project always asks, and the one that decides the request.
     Name the specific corruption, then name the test: what injected fault makes the new
     control fire, and what healthy case proves it stays quiet? A control that has never
     been observed to fail is not a control. -->

Fault:

Proof of firing (`faults.py` injector + case in the matrix):

Proof of silence on healthy data:

## Blind spots

<!-- What would this control NOT see? Every control in this repo documents its blind spots
     on the function itself, rather than leaving them for a customer to discover. -->
