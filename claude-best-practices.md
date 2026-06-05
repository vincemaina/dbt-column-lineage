# CLAUDE HACKS

# Git Management

Always leave git management to me — commits, pushes, branches, tags, rebases, merges, stashes. Do not run any of these on your own. Suggest commit messages or describe the diff if useful, but do not execute the git commands yourself.

If I explicitly tell you to perform a git action ("go ahead and commit this", "push the branch"), treat it as a one-time exception for that specific task. Do not adopt it as a new default. The next time the work is in a committable state, wait for me again.

Reason: git operations are visible to others and hard to reverse. I want to review every change before it's recorded in history.

# Subfolder [CLAUDE.md](http://CLAUDE.md)

Experimenting with having [CLAUDE.md](http://CLAUDE.md) files in every subfolder

* Describes every file \+ subfolder in that folder  
* Setup test to check every subfolder has a [CLAUDE.md](http://CLAUDE.md) file, and that the [CLAUDE.md](http://CLAUDE.md) file references all the files inside that folder

# Claude Skills

Encouraging Claude to make skills as it goes.  
Useful for working with external tools \+ apis \+ packages.

1. Get claude to do web research on using the tool  
2. Get claude to create a skill that has what it’s learned  
3. Restart claude code to make the new skill available

# Isolated Environments

Preferably VMs, but docker containers are an acceptable middle ground.

**Container approach**  
Inside a local repo, you can add a Dockerfile and docker-compose.yaml \+ a bash script that allows you to create a container that shares the same working directory via file-mounts.  
This means you have claude running in a isolated container, with auto-mode or dangerously skip permissions — while still being able to view files and manage commits via an IDE.

**VM approach**  
Similar to above, except the code and runtime lives on an entirely different machine.  
This is more expensive, but requires spending some money, if you don’t have your own local  
VM.

# Web Research

I’ve noticed, getting Claude to do web research before doing work massively improves performance.

# Test Suites

Test suites are great as it’s an easy way for Claude to catch regression issues, without having to go back and check everything itself.  
It’s also useful for enforcing some claude practises we want e.g. having [CLAUDE.md](http://CLAUDE.md) in every folder.  
So tests can be used not just to monitor the code, but also to monitor Claude’s working practises.

# Roadmaps

Roadmaps are the best starting point for a project.  
It helps keep both the agent and I clear on where we’re going, what’s been done etc.  
Now this doesn’t have to be one big roadmap file — you can have one [ROADMAP.md](http://ROADMAP.md) that provides a high-level summary that then links to individual roadmap files for each layer of the project e.g. feature by feature, or phase by phase.

# Planning

Getting Claude to create a plan first is always a good idea. It forces Claude to think about what it’s going to do before starting. This is a great opportunity to get Claude to do web research too. Now Claude has its own plan mode, but I think it’s also useful to have these plans committed in git, as it serves as a log of decisions made. It also allows us to have tight coupling between roadmaps and plans, where plans provide the full brief with the context and everything, and the roadmap turns that into actional steps that reference the plan where more context is needed.

# Agentic Loops (End-to-End access)

Giving the agent access to tools like playwright (or other similar agent browsers) is a great way to allow the agent to test its own work, and check that things are working before telling me the work is done.  
Of course the playwright example is specific to web dev. But the core idea is just giving the agent access to the source code as well as the end product, allowing it to do it’s own end-to-end testing.  
Perhaps we could also encourage it to create end-to-end tests in addition to unit tests and integration tests.

# Smaller Models

I’ve been using Haiku today and honestly it’s doing a great job for the project I’m currently working on (lyst-sprint-assistant). It’s still getting everything right, but just doing it much faster and much cheaper. The only inconvenience is the very small context window, which I’m going through pretty quickly.  
But other than that it’s all pros for this project:

- MUCH faster  
- MUCH cheaper

I think the simpler Haiku model can be effective if you’ve built your project well. In my case, I’m creating loads of [CLAUDE.md](http://CLAUDE.md) files and skills, so haiku is able to understand the context of things easily without having to interpret code itself.  
And because it’s running in a container with end-to-end access it can sort of brute force it’s way to the correct solution. I.e. it doesn’t have to be really clever and anticipate everything from the get-go. It can just build and fix issues as it comes across them.

# Subagents \+ Worktrees

Ideally enabling agents to spawn subagents can be very powerful for a number of reasons.  
The obvious one is you can get more done, faster.  
But also it’s quite efficient for context windows as each subagent has its own context window. So main agent can process a user request or roadmap batch, and then spin up subagents to actually do the work. Those subagents can choose the skills they need to complete the task, as well as store their own context from coming across [CLAUDE.md](http://CLAUDE.md) files. These won’t pollute the context windows of other subagents working on different tasks. So everything in the context window is highly relevant to the task being worked on, and then when the task is done, the subagent is dropped and the context window is cleared — vs working in the main agent where the context window just grows and grows.

# Claude’s thoughts on what’s going well

I asked Claude in a project session what it thinks is going well and what could be better.  
Here’s what it said:

What's working really well:                                                                                                                                                                                                                                                                                                  
     
  1\. Small, focused files \+ CLAUDE.md everywhere — This is the biggest win. I can understand a 200-file codebase by reading \~20 CLAUDE.md summaries and filenames instead of opening files. This saves enormous amounts of context and speeds up orientation.                                                                  
  2\. Persistent memory system — Not re-explaining the project, your preferences, and patterns every session is huge for token efficiency. I can pick up where we left off.  
  3\. Clear architectural constraints in CLAUDE.md — Knowing "lib owns disk I/O," "providers are read-only," etc. means I make correct decisions without asking. This prevents wasted back-and-forth.                                                                                                                           
  4\. Plan mode \+ explicit approval before coding — We align on approach once, then I can execute. No rework from misaligned assumptions.                                                                                                                                                                                       
  5\. Git history as context — Recent commits tell me what's been done and the direction. Saves asking "what should I assume about this?"                                                                                                                                                                                       
  6\. Test suite with fast feedback — Running 272 tests in 1 second means I catch my mistakes immediately, not after you reload the browser.                                                                                                                                                                                    
                                                                                                                                                                                                                                                                                                                               
  What could level up for bigger batches:                                                                                                                                                                                                                                                                                      
                                                                                                                                                                                                                                                                                                                               
  1\. README.md files in key directories — Beyond just CLAUDE.md summaries, a human-readable "here's how these pieces talk to each other" narrative. The web/ README is great; more like that in storage/, providers/, etc.                                                                                                     
  2\. Type checking in CI — Add mypy or similar. Right now I rely on tests to catch type errors; type checking would catch them faster and let me refactor more confidently.  
  3\. More integration tests — The new web tests are good; extending this pattern to storage layer, providers, and their boundaries would let me refactor fearlessly.                                                                                                                                                           
  4\. Clearer data-flow diagrams — ASCII diagrams in key CLAUDE.md files showing "snapshot flows through storage → web → template" help me understand where to touch code.                                                                                                                                                      
  5\. Explicit "definition of done" — When you give me a feature, tell me: "Done means: code compiles, 272 tests pass, web UI works on these flows, no console errors." Lets me self-verify.                                                                                                                                    
  6\. Acceptance test hints — Like "verify this by navigating to /tickets/AENG-2527, clicking Related PRs, and checking they're clickable." Saves me guessing what you'll test.                                                                                                                                                 
                                                                                                                                                                                                                                                                                                                               
  For scaling to bigger batches:                                                                                                                                                                                                                                                                                               
                                                                                                                                                                                                                                                                                                                               
  \- Sub-agents for parallel work — Already possible. I can spin up an agent to explore the codebase while I work on something else. Just needs explicit go-ahead in the prompt.                                                                                                                                                
  \- Isolation with worktrees — You mentioned avoiding worktrees under Docker, but if we're doing bigger parallel work, isolated branches for different tasks would prevent merge conflicts.  
  \- Staged rollout — Instead of "implement feature X," maybe "implement API layer, verify tests, then UI layer, verify tests." Smaller checkpoints.                                                                                                                                                                            
                                                                                                                                                                                                                                                                                                                               
  Token/speed efficiency specifically:                                                                                                                                                                                                                                                                                         
                                                                                                                                                                                                                                                                                                                               
  \- Memoization in my memory system — I'm already doing this (storing architectural principles, user preferences), but being more aggressive about caching decisions ("when refactoring storage, always preserve the one-read-one-write symmetry") saves re-thinking.                                                          
  \- Grep before Read — I'm already doing this, but having a .clodeignore or similar to exclude large generated files, logs, and node\_modules from grep scope would speed up searches.  
  \- Lazy CLAUDE.md updates — Right now I update CLAUDE.md carefully with every change. A faster approach: commit code, update CLAUDE.md in a follow-up batch when the feature stabilizes. Trades documentation lag for speed.                                                                                                  
                                                                                                                                                                                                                                                                                                                               
  The workflow is already pretty solid — the small files \+ memory \+ tests \+ plan mode combination is doing a lot of the heavy lifting. The main gaps are around confidence (more tests) and communication (clearer acceptance criteria, diagrams).      
