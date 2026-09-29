# Example review card

Copied from `output/review.md` (the new-ticket card for the search-lag bug that three customers reported). The data is fictional, so nothing is redacted.

### 25. Bug · P3 · Search index lags ~10 minutes after team rename or member move

`new:call-006#f0` · awaiting review · 3 call(s), 3 account(s): Copperline Energy, Gable Group, Harborline Media

> "There's a real bug we hit over and over, and it's about search, not the editing. After we rename a team or move a member, search keeps returning the old state for about ten minutes."  (Harborline Media, 2026-06-18, [call-006 L24](../../transcripts/call-006.md#L24))
>  - L26 external Aisha: So say I rename "Digital Video" to "Video Production." Somebody searches "Video Production" — the new name — and gets nothing. Empty. Or they search for a person I just moved, and search still shows them filed under the 
>  - L28 external Aisha: That's exactly what it looks like. And I can reproduce it on demand — I did it three times while I was documenting it for myself. Rename a test team, search immediately, stale result. Wait ten minutes, search again, corr
>  - L30 external Aisha: Feels like about ten, give or take a couple. I didn't stopwatch it precisely, but it's in that ballpark consistently. Never seen it take an hour, never seen it be instant.
>  - L34 external Aisha: Oh, it was a mess. It caused a stream of "where did this person go" tickets to my desk. A manager would search for someone right after I moved them, get the old team or get nothing, and conclude I'd deleted the person or

> "search for the new team name right after renaming it, and you get nothing. Empty results, like the team doesn't exist."  (Gable Group, 2026-06-21, [call-012 L18](../../transcripts/call-012.md#L18))
>  - L16 external Devon: Feedback, yes. Mostly one thing, repeatedly, and it's a real one. We merged those two departments this month, which meant renaming teams and moving about forty people around. And every single time we made a change, searc
>  - L19 internal Sam: So the edit is applied, the change is saved, but search keeps serving the old state for several minutes before catching up.
>  - L20 external Devon: That's exactly it. And it was consistent enough that my admins started planning around it. I'm not kidding — they started setting literal kitchen timers. Make a batch of changes, set a ten-minute timer, don't trust searc
>  - L22 external Devon: Consistent enough to plan around, yes. And look, I'm a systems person — I get it, indexes take time to rebuild, eventual consistency is a real thing, I'm not naive about it. But here's my actual complaint: nothing in the

> "When we rename a team or move people between teams — which we do a lot during reorgs — the changes don't seem to show up right away when you search."  (Copperline Energy, 2026-06-16, [call-072 L29](../../transcripts/call-072.md#L29))
>  - L33 external Gerald Voss: That's the thing — if they come back ten, fifteen minutes later, it's fine. It fixes itself. So it's not broken exactly, it's just... slow to catch up.
>  - L36 external Priti Shah: I've hit this too actually. I moved someone to my cohort and couldn't find them under the new team for a while. I assumed I did it wrong and re-did it, which probably didn't help.
>  - L42 external Gerald Voss: Consistently around ten minutes. Sometimes a touch less. Never seen it take an hour or anything. Just enough to be annoying.
>  - L44 external Gerald Voss: Good question. Let me think. Yeah — if I click into the team directly, the new name and the new members are right. It's when you search by name that you get the old picture for a while.

- **Why new, not an existing issue:** Distinct from PROJ-131 (new invites not searchable until next day's index build): this is a ~10-minute lag on renames/moves for existing teams/members, not a next-day delay scoped to newly invited members.
- **Priority P3 (medium):** Real, reproducible defect causing confusion and support tickets during high-edit periods, but data is not lost, it self-corrects in ~10 minutes, and there is a known workaround (wait and re-search); customer explicitly says it is not urgent.
- **Grouped because:** All three describe the identical bug: after an admin renames a team or moves a member, search results remain stale for ~10 minutes (old name/team shown, or empty for new name) before self-correcting, while the underlying save/edit itself succeeds immediately. Same symptom, same scope (search index propagation delay), reported by different customers during reorg events.
- **Slack:** @tomas.vela, @sam.oduya, @maya.chen
- **Approve:** `python -m solution approve 'new:call-006#f0'`

<details><summary>Exact Jira payload</summary>

```json
{
 "corroborating_sources": [
  {
   "call_id": "call-012",
   "line": 18,
   "link": "transcripts/call-012.md#L18",
   "snippet": "search for the new team name right after renaming it, and you get nothing. Empty results, like the team doesn't exist."
  },
  {
   "call_id": "call-072",
   "line": 29,
   "link": "transcripts/call-072.md#L29",
   "snippet": "When we rename a team or move people between teams — which we do a lot during reorgs — the changes don't seem to show up right away when you search."
  }
 ],
 "description": "After renaming a team or moving a member in the admin panel, search returns stale/old results (empty for the new team name, or old team for a moved member) for approximately 10 minutes before self-correcting with no user action required. Customer reproduced this on demand three separate times with consistent ~10 minute timing. During a large-scale reorg (60 members moved, 5 teams collapsed to 3 over two days), this caused a stream of 'where did this person go' tickets from managers who searched immediately after changes and concluded people had been deleted. The underlying edit/save operations (bulk move, rename) work correctly and do not lose data; only the search index is delayed. Workaround is waiting ~10 minutes for the index to catch up.\n\n*Reported on 3 call(s) by 3 account(s):* Copperline Energy, Gable Group, Harborline Media\n\n> \"There's a real bug we hit over and over, and it's about search, not the editing. After we rename a team or move a member, search keeps returning the old state for about ten minutes.\"  (Harborline Media, call-006 2026-06-18, transcripts/call-006.md#L24)\n> \"search for the new team name right after renaming it, and you get nothing. Empty results, like the team doesn't exist.\"  (Gable Group, call-012 2026-06-21, transcripts/call-012.md#L18)\n> \"When we rename a team or move people between teams — which we do a lot during reorgs — the changes don't seem to show up right away when you search.\"  (Copperline Energy, call-072 2026-06-16, transcripts/call-072.md#L29)\n\n_Severity medium: Real, reproducible defect causing confusion and support tickets during high-edit periods, but data is not lost, it self-corrects in ~10 minutes, and there is a known workaround (wait and re-search); customer explicitly says it is not urgent._\n_Drafted by june-tapes from customer-call transcripts; reviewed and approved by a human before filing._",
 "idempotency_key": "jt-e184470eb555df81",
 "labels": [
  "customer-call",
  "june-tapes"
 ],
 "priority": "P3",
 "project": "PROJ",
 "source": {
  "call_id": "call-006",
  "line": 24,
  "link": "transcripts/call-006.md#L24",
  "snippet": "There's a real bug we hit over and over, and it's about search, not the editing. After we rename a team or move a member, search keeps returning the old state for about ten minutes."
 },
 "summary": "Search index lags ~10 minutes after team rename or member move",
 "type": "Bug"
}
```
</details>
