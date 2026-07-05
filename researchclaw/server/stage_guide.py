"""Plain-English guide to the 23 pipeline stages, written for non-technical readers."""

from __future__ import annotations

STAGE_GUIDE: list[dict] = [
    {
        "num": 1,
        "key": "TOPIC_INIT",
        "title": "Understanding your idea",
        "phase": "Scoping",
        "what": (
            "The system reads your topic and turns it into a clear, written research "
            "goal so everyone (you and the AI) agrees on what we're actually trying to "
            "find out. It also takes stock of the computer it's running on, so later "
            "experiments are designed to fit the hardware available."
        ),
        "reads": "The topic you typed in, plus details about the machine the research will run on.",
        "produces": "A written statement of the research goal, and a profile of the available hardware.",
        "is_gate": False,
        "reasoning_file": "goal.md",
    },
    {
        "num": 2,
        "key": "PROBLEM_DECOMPOSE",
        "title": "Breaking it into research questions",
        "phase": "Scoping",
        "what": (
            "Big ideas are too broad to test directly, so this stage breaks your goal "
            "into a tree of smaller, concrete questions. It also honestly evaluates "
            "whether the topic is feasible and worth pursuing, which keeps the project "
            "from chasing something vague or impossible."
        ),
        "reads": "The research goal from the previous stage.",
        "produces": "A map of specific sub-questions, and an assessment of how promising the topic is.",
        "is_gate": False,
        "reasoning_file": "problem_tree.md",
    },
    {
        "num": 3,
        "key": "SEARCH_STRATEGY",
        "title": "Planning the literature search",
        "phase": "Literature",
        "what": (
            "Before reading anything, the system plans how it will search: which "
            "databases and websites to look in, and exactly which search phrases to "
            "use. A deliberate plan makes the literature review thorough and "
            "repeatable instead of haphazard."
        ),
        "reads": "The research questions from the scoping phase.",
        "produces": "A search plan listing the sources it will check and the queries it will run.",
        "is_gate": False,
        "reasoning_file": "search_plan.yaml",
    },
    {
        "num": 4,
        "key": "LITERATURE_COLLECT",
        "title": "Collecting papers",
        "phase": "Literature",
        "what": (
            "The system carries out the search plan, gathering candidate research "
            "papers and useful web context from the sources it chose. This casts a "
            "wide net on purpose — it's better to collect too much now and filter "
            "later than to miss something important."
        ),
        "reads": "The search plan and queries from the previous stage.",
        "produces": "A pile of candidate papers with their bibliographic details, plus notes on how the search went.",
        "is_gate": False,
        "reasoning_file": "search_meta.json",
    },
    {
        "num": 5,
        "key": "LITERATURE_SCREEN",
        "title": "Screening for relevance",
        "phase": "Literature",
        "what": (
            "Every collected paper is judged for relevance and quality, and only the "
            "genuinely useful ones make the shortlist. This is a checkpoint stage: "
            "the pipeline pauses here so a human can confirm the shortlist looks "
            "right before deeper work begins."
        ),
        "reads": "The full pile of candidate papers.",
        "produces": "A shortlist of the papers worth reading closely, with notes on why each was kept or dropped.",
        "is_gate": True,
        "reasoning_file": "screen_meta.json",
    },
    {
        "num": 6,
        "key": "KNOWLEDGE_EXTRACT",
        "title": "Extracting key findings",
        "phase": "Literature",
        "what": (
            "Each shortlisted paper is read closely and condensed into a structured "
            "note card: what the paper found, how it found it, and its limitations. "
            "These cards become the raw material for understanding the field without "
            "re-reading whole papers later."
        ),
        "reads": "The shortlisted papers.",
        "produces": "One summary card per paper, capturing its key findings, methods, and caveats.",
        "is_gate": False,
        "reasoning_file": "cards",
    },
    {
        "num": 7,
        "key": "SYNTHESIS",
        "title": "Synthesizing what's known",
        "phase": "Hypothesis",
        "what": (
            "The individual paper cards are woven together into a single narrative of "
            "the field: what's established, where researchers disagree, and — most "
            "importantly — what nobody has answered yet. Those gaps are where a new "
            "contribution can live."
        ),
        "reads": "All the summary cards from the literature phase.",
        "produces": "A written synthesis of the state of the field, highlighting open gaps and opportunities.",
        "is_gate": False,
        "reasoning_file": "synthesis.md",
    },
    {
        "num": 8,
        "key": "HYPOTHESIS_GEN",
        "title": "Forming the hypothesis",
        "phase": "Hypothesis",
        "what": (
            "Drawing on the gaps found in the synthesis, the system proposes specific, "
            "testable hypotheses. It debates them from multiple perspectives and "
            "checks each one for novelty, so the project ends up testing an idea "
            "that is both new and actually answerable."
        ),
        "reads": "The synthesis of the field and the original research questions.",
        "produces": "One or more candidate hypotheses, the arguments for and against each, and a novelty check.",
        "is_gate": False,
        "reasoning_file": "perspectives",
    },
    {
        "num": 9,
        "key": "EXPERIMENT_DESIGN",
        "title": "Designing the experiments",
        "phase": "Experiments",
        "what": (
            "The chosen hypothesis is turned into a concrete experiment plan: what to "
            "measure, what to compare against, and how success will be judged. This "
            "is a checkpoint stage — the pipeline pauses so a human can approve the "
            "plan before any code is written or compute is spent."
        ),
        "reads": "The hypothesis and the hardware profile from earlier stages.",
        "produces": "A detailed experiment plan, including comparisons, measurements, and success criteria.",
        "is_gate": True,
        "reasoning_file": "exp_plan.yaml",
    },
    {
        "num": 10,
        "key": "CODE_GENERATION",
        "title": "Writing the experiment code",
        "phase": "Experiments",
        "what": (
            "The experiment plan is translated into working computer code. The code "
            "is then validated and reviewed for correctness before anything runs, "
            "because a bug here would quietly poison every result that follows."
        ),
        "reads": "The approved experiment plan.",
        "produces": "The experiment code itself, plus a validation report and a code review.",
        "is_gate": False,
        "reasoning_file": "validation_report.md",
    },
    {
        "num": 11,
        "key": "RESOURCE_PLANNING",
        "title": "Planning compute resources",
        "phase": "Experiments",
        "what": (
            "Before pressing 'go', the system schedules the experiment runs: how long "
            "each should take, in what order they'll run, and whether they fit the "
            "available hardware and time budget. This prevents surprises like an "
            "experiment that would take a week on the current machine."
        ),
        "reads": "The experiment code and the hardware profile.",
        "produces": "A run schedule with time and resource estimates for each experiment.",
        "is_gate": False,
        "reasoning_file": "schedule.json",
    },
    {
        "num": 12,
        "key": "EXPERIMENT_RUN",
        "title": "Running the experiments",
        "phase": "Experiments",
        "what": (
            "The moment of truth: the experiments actually execute according to the "
            "schedule, and every run's output is recorded. Careful record-keeping "
            "here is what makes the eventual results trustworthy and reproducible."
        ),
        "reads": "The experiment code and the run schedule.",
        "produces": "The raw results of every run, plus a history of what ran, when, and how it went.",
        "is_gate": False,
        "reasoning_file": "runs/results.json",
    },
    {
        "num": 13,
        "key": "ITERATIVE_REFINE",
        "title": "Refining the experiments",
        "phase": "Experiments",
        "what": (
            "First attempts rarely go perfectly. This stage examines the initial "
            "results, fixes problems, tunes settings, and re-runs where needed — "
            "keeping a log of every change so the final experiment is both better "
            "and fully accounted for."
        ),
        "reads": "The raw results and any errors or oddities from the first runs.",
        "produces": "An improved final version of the experiment, and a log explaining each refinement made.",
        "is_gate": False,
        "reasoning_file": "refinement_log.json",
    },
    {
        "num": 14,
        "key": "RESULT_ANALYSIS",
        "title": "Analyzing the results",
        "phase": "Analysis",
        "what": (
            "The numbers from the experiments are interpreted: did they support the "
            "hypothesis, and how confident can we be? The analysis is deliberately "
            "argued from several perspectives, including a skeptical one, to guard "
            "against wishful thinking."
        ),
        "reads": "The final experiment results.",
        "produces": "A written analysis of what the results mean, examined from multiple viewpoints.",
        "is_gate": False,
        "reasoning_file": "analysis.md",
    },
    {
        "num": 15,
        "key": "RESEARCH_DECISION",
        "title": "Deciding how to proceed",
        "phase": "Analysis",
        "what": (
            "Based on the analysis, the system makes an honest call: are the findings "
            "strong enough to write up, do the experiments need another round, or "
            "should the hypothesis be revised? Writing this decision down keeps the "
            "project from drifting into a paper that overclaims."
        ),
        "reads": "The result analysis and the original hypothesis.",
        "produces": "A clear, reasoned decision about the path forward, in both readable and structured form.",
        "is_gate": False,
        "reasoning_file": "decision.md",
    },
    {
        "num": 16,
        "key": "PAPER_OUTLINE",
        "title": "Outlining the paper",
        "phase": "Writing",
        "what": (
            "Before any prose is written, the paper's skeleton is laid out: what each "
            "section will argue, which results go where, and how the story flows from "
            "question to answer. A strong outline makes the draft coherent instead of "
            "a list of disconnected facts."
        ),
        "reads": "The analysis, the decision, and the literature synthesis.",
        "produces": "A section-by-section outline of the paper.",
        "is_gate": False,
        "reasoning_file": "outline.md",
    },
    {
        "num": 17,
        "key": "PAPER_DRAFT",
        "title": "Writing the draft",
        "phase": "Writing",
        "what": (
            "The outline is expanded into a full first draft of the research paper, "
            "complete with citations to the literature gathered earlier. The draft is "
            "also self-scored on quality, so weak sections are flagged before review."
        ),
        "reads": "The outline, the results, and the paper summary cards.",
        "produces": "A complete draft of the paper, plus a quality assessment of the draft.",
        "is_gate": False,
        "reasoning_file": "draft_quality.json",
    },
    {
        "num": 18,
        "key": "PEER_REVIEW",
        "title": "Running peer review",
        "phase": "Writing",
        "what": (
            "The draft is critiqued the way journal reviewers would critique it: "
            "independent reviewer personas hunt for weak arguments, missing evidence, "
            "and unclear writing. Facing this criticism now means the final paper can "
            "answer it in advance."
        ),
        "reads": "The complete paper draft.",
        "produces": "A set of written reviews listing the draft's strengths, weaknesses, and required fixes.",
        "is_gate": False,
        "reasoning_file": "reviews.md",
    },
    {
        "num": 19,
        "key": "PAPER_REVISION",
        "title": "Revising the paper",
        "phase": "Writing",
        "what": (
            "The draft is rewritten to address every point the reviewers raised, and "
            "an internal note records exactly how each criticism was handled. This is "
            "the same revise-and-respond cycle human researchers go through before "
            "publication."
        ),
        "reads": "The draft and the peer reviews.",
        "produces": "A revised paper, plus notes documenting how each review comment was addressed.",
        "is_gate": False,
        "reasoning_file": "revision_notes_internal.md",
    },
    {
        "num": 20,
        "key": "QUALITY_GATE",
        "title": "Final quality checks",
        "phase": "Finalizing",
        "what": (
            "The revised paper goes through strict final checks — including a scan "
            "for any claims or numbers that aren't backed by the actual experiment "
            "records. This is a checkpoint stage: nothing moves forward until the "
            "paper passes, protecting you from publishing anything fabricated or unsound."
        ),
        "reads": "The revised paper and the underlying experiment records.",
        "produces": "A quality report, and a list of any statements flagged as unsupported by the evidence.",
        "is_gate": True,
        "reasoning_file": "quality_report.json",
    },
    {
        "num": 21,
        "key": "KNOWLEDGE_ARCHIVE",
        "title": "Archiving what was learned",
        "phase": "Finalizing",
        "what": (
            "Everything the project learned — findings, dead ends, and lessons — is "
            "packaged into a tidy archive with an index of all the artifacts. Future "
            "research projects can build on this record instead of starting from zero."
        ),
        "reads": "All the outputs produced across the pipeline.",
        "produces": "A written archive of lessons learned and an index of everything the project created.",
        "is_gate": False,
        "reasoning_file": "archive.md",
    },
    {
        "num": 22,
        "key": "EXPORT_PUBLISH",
        "title": "Exporting the deliverables",
        "phase": "Finalizing",
        "what": (
            "The finished paper is prepared in shareable formats — a readable "
            "document, a typeset-ready version, and its bibliography. The content is "
            "also sanitized to remove anything internal or sensitive before it leaves "
            "the system."
        ),
        "reads": "The final approved paper and its reference list.",
        "produces": "The final paper in publishable formats, with its full bibliography.",
        "is_gate": False,
        "reasoning_file": "sanitization_report.json",
    },
    {
        "num": 23,
        "key": "CITATION_VERIFY",
        "title": "Verifying every citation",
        "phase": "Finalizing",
        "what": (
            "Every reference in the paper is checked against real, findable sources "
            "to confirm it actually exists and says what the paper claims. This final "
            "safeguard catches invented or mismatched citations — one of the most "
            "damaging mistakes a paper can contain."
        ),
        "reads": "The final paper and its bibliography.",
        "produces": "A verification report for every citation, and a bibliography containing only confirmed references.",
        "is_gate": False,
        "reasoning_file": "verification_report.json",
    },
]

STAGE_BY_NUM: dict[int, dict] = {d["num"]: d for d in STAGE_GUIDE}
