from dataclasses import dataclass, field


@dataclass
class ConversationState:
    loan_amount: str | None = None
    business_type: str | None = None
    business_age: str | None = None
    loan_purpose: str | None = None

    qualification_active: bool = False
    escalation_requested: bool = False

    history: list[dict] = field(default_factory=list)

    def add_turn(self, role: str, text: str) -> None:
        self.history.append({
            "role": role,
            "text": text,
        })

    @property
    def qualification_complete(self) -> bool:
        return all([
            self.loan_amount,
            self.business_type,
            self.business_age,
            self.loan_purpose,
        ])

    def summary(self) -> dict:
        return {
            "active": self.qualification_active,
            "loan_amount": self.loan_amount,
            "business_type": self.business_type,
            "business_age": self.business_age,
            "loan_purpose": self.loan_purpose,
            "qualification_complete": self.qualification_complete,
            "escalation_requested": self.escalation_requested,
        }


def detect_escalation(text: str) -> bool:
    text = text.lower()

    escalation_phrases = [
        "talk to a human",
        "talk to someone",
        "human agent",
        "human representative",
        "speak to a person",
        "speak with someone",
        "real person",
        "customer service",
        "representative",
        "call me",
    ]

    return any(
        phrase in text
        for phrase in escalation_phrases
    )


def detect_qualification_intent(text: str) -> bool:
    text = text.lower()

    keywords = [
        "business loan",
        "loan",
        "funding",
        "finance",
        "financing",
    ]

    return any(
        keyword in text
        for keyword in keywords
    )


def next_qualification_question(
    state: ConversationState,
) -> str | None:

    if not state.loan_amount:
        return "How much funding are you looking for?"

    if not state.business_type:
        return "What type of business do you operate?"

    if not state.business_age:
        return "How long has your business been operating?"

    if not state.loan_purpose:
        return "What will you use the loan for?"

    return None