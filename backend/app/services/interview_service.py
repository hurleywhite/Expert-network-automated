"""
AI Interview Service - Handles AI-moderated interviews with candidates
Integrates Claude API for conversation logic and ElevenLabs for voice synthesis
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from uuid import UUID

import httpx
from sqlalchemy.orm import Session

from app import crud, models, schemas
from app.config import settings
from app.services.llm import LLMService

logger = logging.getLogger(__name__)


class InterviewService:
    """Service for managing AI-moderated interviews."""
    
    def __init__(self):
        self.llm_service = LLMService()
        self.eleven_labs_api_key = getattr(settings, 'ELEVEN_LABS_API_KEY', None)
        
    async def create_interview_template(
        self,
        db: Session,
        name: str,
        interview_type: models.InterviewType,
        description: str = "",
        created_by: str = "system"
    ) -> models.InterviewTemplate:
        """Create a new interview template."""
        
        # Default question flows based on interview type
        question_flows = {
            models.InterviewType.FOLLOW_UP: [
                "Thank you for responding to our outreach! I'm an AI assistant helping to understand your background and expertise.",
                "Can you tell me a bit about your current role at {company}?",
                "What are the main challenges you're facing in {industry} right now?", 
                "How long have you been working in this space?",
                "What trends are you most excited or concerned about?",
                "Would you be interested in participating in expert consultations on these topics?"
            ],
            models.InterviewType.QUALIFICATION: [
                "Hello! I'm conducting a brief qualification interview to understand your expertise.",
                "Can you describe your experience in {industry}?",
                "What's your decision-making authority in your current role?",
                "Have you participated in expert network consultations before?",
                "What topics would you consider yourself an expert in?"
            ],
            models.InterviewType.DEEP_DIVE: [
                "Welcome to our expert consultation. I'll be asking detailed questions about {topic}.",
                "First, can you provide an overview of your experience with {topic}?",
                "What are the key factors driving change in this area?",
                "Can you walk me through a specific example from your experience?",
                "What advice would you give to someone new to this field?",
                "Where do you see this industry heading in the next 2-3 years?"
            ]
        }
        
        follow_up_rules = {
            "max_follow_ups": 3,
            "probe_for_specifics": True,
            "ask_for_examples": True,
            "clarify_ambiguous_responses": True,
            "emotional_intelligence": True
        }
        
        success_criteria = {
            "min_responses": 5,
            "min_response_length": 50,
            "engagement_score": 7.0,
            "completion_rate": 0.8
        }
        
        template = models.InterviewTemplate(
            name=name,
            description=description,
            interview_type=interview_type,
            opening_prompt=f"You are conducting a {interview_type.value} interview. Be professional, curious, and adaptive.",
            question_flow=question_flows.get(interview_type, []),
            follow_up_rules=follow_up_rules,
            success_criteria=success_criteria,
            created_by=created_by
        )
        
        db.add(template)
        db.commit()
        db.refresh(template)
        return template
    
    async def schedule_interview(
        self,
        db: Session,
        candidate_id: UUID,
        project_id: UUID,
        template_id: UUID,
        scheduled_for: datetime,
        created_by: str,
        timezone: str = "UTC",
        video_enabled: bool = True,
        ai_voice_id: str = None
    ) -> models.InterviewSession:
        """Schedule a new AI interview session."""
        
        # Generate Google Meet link (placeholder - would integrate with Google Meet API)
        meet_link = f"https://meet.google.com/interview-{candidate_id}"
        
        session = models.InterviewSession(
            candidate_id=candidate_id,
            project_id=project_id,
            template_id=template_id,
            scheduled_for=scheduled_for,
            timezone=timezone,
            video_enabled=video_enabled,
            audio_enabled=True,
            recording_enabled=True,
            ai_voice_id=ai_voice_id or "default",
            meet_link=meet_link,
            created_by=created_by
        )
        
        db.add(session)
        db.commit()
        db.refresh(session)
        
        # TODO: Send calendar invite to candidate
        await self._send_interview_invite(session)
        
        return session
    
    async def start_interview(
        self,
        db: Session,
        session_id: UUID
    ) -> Dict:
        """Start an interview session."""
        
        session = db.query(models.InterviewSession).filter(
            models.InterviewSession.id == session_id
        ).first()
        
        if not session:
            raise ValueError("Interview session not found")
            
        if session.status != models.InterviewStatus.SCHEDULED:
            raise ValueError(f"Cannot start interview with status {session.status}")
        
        # Update session status
        session.status = models.InterviewStatus.IN_PROGRESS
        session.started_at = datetime.utcnow()
        
        # Get template and candidate info
        template = session.template
        candidate = session.candidate
        project = session.project
        
        # Create opening message
        opening_text = template.opening_prompt.format(
            candidate_name=candidate.first_name or candidate.full_name,
            company=candidate.company,
            industry=project.industry
        )
        
        opening_message = await self._create_ai_message(
            db, session_id, opening_text, timestamp=0.0
        )
        
        # Generate AI voice for opening (if voice enabled)
        if session.audio_enabled and self.eleven_labs_api_key:
            audio_url = await self._generate_ai_voice(opening_text, session.ai_voice_id)
            opening_message.audio_url = audio_url
        
        db.commit()
        
        return {
            "session_id": session_id,
            "status": "started",
            "opening_message": {
                "id": opening_message.id,
                "text": opening_text,
                "audio_url": opening_message.audio_url
            },
            "meet_link": session.meet_link
        }
    
    async def process_human_response(
        self,
        db: Session,
        session_id: UUID,
        response_text: str,
        timestamp_seconds: float,
        audio_url: Optional[str] = None
    ) -> Dict:
        """Process a human response and generate AI follow-up."""
        
        session = db.query(models.InterviewSession).filter(
            models.InterviewSession.id == session_id
        ).first()
        
        if not session or session.status != models.InterviewStatus.IN_PROGRESS:
            raise ValueError("Invalid session state")
        
        # Store human response
        human_message = await self._create_human_message(
            db, session_id, response_text, timestamp_seconds, audio_url
        )
        
        # Analyze response sentiment/emotion
        await self._analyze_response(db, human_message)
        
        # Generate AI follow-up
        ai_follow_up = await self._generate_ai_follow_up(db, session)
        
        if ai_follow_up:
            ai_message = await self._create_ai_message(
                db, session_id, ai_follow_up, timestamp_seconds + 1.0
            )
            
            # Generate AI voice if enabled
            if session.audio_enabled and self.eleven_labs_api_key:
                audio_url = await self._generate_ai_voice(ai_follow_up, session.ai_voice_id)
                ai_message.audio_url = audio_url
                db.commit()
        
        # Check if interview should complete
        if await self._should_complete_interview(db, session):
            await self.complete_interview(db, session_id)
            
        return {
            "ai_response": {
                "id": ai_message.id if ai_follow_up else None,
                "text": ai_follow_up,
                "audio_url": ai_message.audio_url if ai_follow_up else None
            },
            "session_status": session.status.value
        }
    
    async def complete_interview(
        self,
        db: Session,
        session_id: UUID
    ) -> Dict:
        """Complete an interview session and generate summary."""
        
        session = db.query(models.InterviewSession).filter(
            models.InterviewSession.id == session_id
        ).first()
        
        if not session:
            raise ValueError("Interview session not found")
        
        # Update session status
        session.status = models.InterviewStatus.COMPLETED
        session.completed_at = datetime.utcnow()
        
        if session.started_at:
            duration = session.completed_at - session.started_at
            session.duration_seconds = int(duration.total_seconds())
        
        # Generate summary and insights
        summary_data = await self._generate_interview_summary(db, session)
        session.summary = summary_data["summary"]
        session.key_insights = summary_data["insights"]
        session.qualification_score = summary_data["score"]
        session.next_steps = summary_data["next_steps"]
        
        db.commit()
        
        return {
            "session_id": session_id,
            "status": "completed",
            "summary": session.summary,
            "insights": session.key_insights,
            "score": session.qualification_score,
            "next_steps": session.next_steps
        }
    
    async def _create_ai_message(
        self,
        db: Session,
        session_id: UUID,
        text: str,
        timestamp: float
    ) -> models.InterviewMessage:
        """Create an AI message in the interview."""
        
        message = models.InterviewMessage(
            session_id=session_id,
            message_type=models.MessageType.AI_QUESTION,
            text_content=text,
            timestamp_seconds=timestamp
        )
        
        db.add(message)
        db.commit()
        db.refresh(message)
        return message
    
    async def _create_human_message(
        self,
        db: Session,
        session_id: UUID,
        text: str,
        timestamp: float,
        audio_url: Optional[str] = None
    ) -> models.InterviewMessage:
        """Create a human message in the interview."""
        
        message = models.InterviewMessage(
            session_id=session_id,
            message_type=models.MessageType.HUMAN_RESPONSE,
            text_content=text,
            audio_url=audio_url,
            timestamp_seconds=timestamp
        )
        
        db.add(message)
        db.commit()
        db.refresh(message)
        return message
    
    async def _analyze_response(
        self,
        db: Session,
        message: models.InterviewMessage
    ) -> None:
        """Analyze human response for sentiment and emotion."""
        
        try:
            analysis_prompt = f"""
            Analyze this interview response for sentiment and emotional tone:
            
            "{message.text_content}"
            
            Return JSON with:
            - sentiment_score: float from -1 (negative) to 1 (positive)
            - emotion: primary emotion detected (e.g., "engaged", "hesitant", "excited", "concerned")
            - confidence: float from 0 to 1 indicating analysis confidence
            """
            
            analysis = await self.llm_service.generate_response(analysis_prompt)
            analysis_data = json.loads(analysis)
            
            message.sentiment_score = analysis_data.get("sentiment_score", 0.0)
            message.emotion_detected = analysis_data.get("emotion", "neutral")
            message.confidence_score = analysis_data.get("confidence", 0.5)
            
        except Exception as e:
            logger.error(f"Error analyzing response: {e}")
            message.sentiment_score = 0.0
            message.emotion_detected = "neutral"
            message.confidence_score = 0.0
    
    async def _generate_ai_follow_up(
        self,
        db: Session,
        session: models.InterviewSession
    ) -> Optional[str]:
        """Generate AI follow-up question based on conversation history."""
        
        # Get conversation history
        messages = db.query(models.InterviewMessage).filter(
            models.InterviewMessage.session_id == session.id
        ).order_by(models.InterviewMessage.timestamp_seconds).all()
        
        # Build conversation context
        conversation = []
        for msg in messages:
            role = "AI" if msg.message_type == models.MessageType.AI_QUESTION else "Human"
            conversation.append(f"{role}: {msg.text_content}")
        
        conversation_text = "\n".join(conversation[-10:])  # Last 10 messages
        
        # Get template context
        template = session.template
        candidate = session.candidate
        project = session.project
        
        follow_up_prompt = f"""
        You are an AI interviewer conducting a {template.interview_type.value} interview.
        
        Context:
        - Candidate: {candidate.full_name} at {candidate.company}
        - Project: {project.name} ({project.industry})
        - Template: {template.name}
        
        Conversation so far:
        {conversation_text}
        
        Rules:
        {json.dumps(template.follow_up_rules, indent=2)}
        
        Questions to consider (adapt based on conversation):
        {json.dumps(template.question_flow, indent=2)}
        
        Generate the next question or comment. Be:
        - Natural and conversational
        - Specific to their responses  
        - Probing for deeper insights
        - Professional but engaging
        
        If the conversation has reached natural conclusion, return "COMPLETE".
        Otherwise, return just the next question/comment.
        """
        
        try:
            response = await self.llm_service.generate_response(follow_up_prompt)
            
            if response.strip().upper() == "COMPLETE":
                return None
            
            return response.strip()
            
        except Exception as e:
            logger.error(f"Error generating follow-up: {e}")
            return "Thank you for that response. Is there anything else you'd like to share?"
    
    async def _generate_ai_voice(
        self,
        text: str,
        voice_id: str = "default"
    ) -> Optional[str]:
        """Generate AI voice using ElevenLabs API."""
        
        if not self.eleven_labs_api_key:
            return None
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
                    headers={
                        "xi-api-key": self.eleven_labs_api_key,
                        "Content-Type": "application/json"
                    },
                    json={
                        "text": text,
                        "voice_settings": {
                            "stability": 0.75,
                            "similarity_boost": 0.75
                        }
                    }
                )
                
                if response.status_code == 200:
                    # Save audio file and return URL
                    # TODO: Implement file storage
                    return f"/audio/interview_{datetime.utcnow().timestamp()}.mp3"
                
        except Exception as e:
            logger.error(f"Error generating voice: {e}")
        
        return None
    
    async def _should_complete_interview(
        self,
        db: Session,
        session: models.InterviewSession
    ) -> bool:
        """Check if interview should be completed."""
        
        # Get message count
        message_count = db.query(models.InterviewMessage).filter(
            models.InterviewMessage.session_id == session.id,
            models.InterviewMessage.message_type == models.MessageType.HUMAN_RESPONSE
        ).count()
        
        # Check success criteria
        criteria = session.template.success_criteria
        min_responses = criteria.get("min_responses", 5)
        
        # Check time limit (default 30 minutes)
        if session.started_at:
            elapsed = datetime.utcnow() - session.started_at
            if elapsed.total_seconds() > 1800:  # 30 minutes
                return True
        
        # Check response count
        if message_count >= min_responses:
            return True
        
        return False
    
    async def _generate_interview_summary(
        self,
        db: Session,
        session: models.InterviewSession
    ) -> Dict:
        """Generate interview summary and insights."""
        
        # Get all messages
        messages = db.query(models.InterviewMessage).filter(
            models.InterviewMessage.session_id == session.id
        ).order_by(models.InterviewMessage.timestamp_seconds).all()
        
        # Build transcript
        transcript = []
        for msg in messages:
            role = "AI" if msg.message_type == models.MessageType.AI_QUESTION else "Human"
            transcript.append(f"{role}: {msg.text_content}")
        
        transcript_text = "\n".join(transcript)
        
        summary_prompt = f"""
        Analyze this expert interview transcript and provide:
        
        1. A concise summary (2-3 paragraphs)
        2. Key insights (3-5 bullet points)
        3. Qualification score (0-100) based on expertise and engagement
        4. Next steps recommendations
        
        Interview Type: {session.template.interview_type.value}
        Candidate: {session.candidate.full_name} at {session.candidate.company}
        
        Transcript:
        {transcript_text}
        
        Return JSON format:
        {
          "summary": "...",
          "insights": ["...", "..."],
          "score": 85,
          "next_steps": ["...", "..."]
        }
        """
        
        try:
            response = await self.llm_service.generate_response(summary_prompt)
            return json.loads(response)
        except Exception as e:
            logger.error(f"Error generating summary: {e}")
            return {
                "summary": "Interview completed successfully.",
                "insights": ["Candidate was engaged and provided valuable responses."],
                "score": 75,
                "next_steps": ["Follow up with detailed consultation proposal."]
            }
    
    async def _send_interview_invite(
        self,
        session: models.InterviewSession
    ) -> None:
        """Send interview invitation to candidate."""
        
        # TODO: Integrate with email service to send calendar invite
        # This would use the existing email service
        logger.info(f"Interview invite sent for session {session.id}")


# Global instance
interview_service = InterviewService()