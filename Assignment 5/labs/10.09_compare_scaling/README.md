# 10.09 · Compare scaling approaches: AReaL-RSI vs SwarmRSI

**Purpose:** distinguish leader-follower coordination (AReaL-RSI) from peer-to-peer swarm evolution (SwarmRSI) before simulating each one (10.10, 10.11).

| Aspect | AReaL-RSI (my lab 10.10) | SwarmRSI (my lab 10.11) |
|---|---|---|
| Coordination | 1 leader chooses an orientation per campaign; 2 researchers execute | 5 peers, each with its own research direction |
| Memory | Conditional: *resolved* findings vs *unresolved* problems, keyed by context | Shared experience table, keyed by (edit, context) |
| Evolution | Evidence-based review re-weights orientations after each campaign | Mutation + complementary recombination + self-revised procedure |
| Selection | Leader-guided | Each agent keeps its own improvements; best agent reported |
| Budget use | Concentrated: one incumbent pipeline | Spread over 5 lineages |

**Advantage of AReaL-RSI.** Every evaluation goes to one incumbent, so a good finding is built on immediately. The conditional memory stops the team repeating a dead end in the same context.

**Limitation of AReaL-RSI.** The leader is a single point of judgement. In my simulation it kept returning to an orientation that had just paid off ("calibration → calibration"), and lost coverage. Lab 10.10 measures this.

**Advantage of SwarmRSI.** Several directions are explored at once, and recombination merges findings that no single agent made (e.g. the calibration agent's firmware fix plus the signal agent's trend feature).

**Limitation of SwarmRSI.** It splits the budget five ways. On a small budget, one focused agent can be better. Lab 10.11 measures this against a single hill-climber.

**When I'd choose each:**
- **AReaL-RSI:** a persistent programme with a clear objective, where findings should accumulate on one system (e.g. keeping one production model improving month after month).
- **SwarmRSI:** an open-ended problem with several plausible root causes, where the parts can be combined, and the budget can cover several lineages.

## Quiz

**Q1. When is leader-follower coordination better than swarm evolution?**
When the direction is clear and the budget is small. Concentrating evaluations on one incumbent beats splitting them.

**Q2. Why must shared memory be *conditional*?**
Because an edit's value depends on context. In TurbineGym, per-turbine z-scoring does nothing on the raw data but helps after the firmware rescale. Unconditional memory would record it as a dead end for everyone.
