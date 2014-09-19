import datetime
import copy
from acj import db
import factory.fuzzy
from acj.models import UserTypesForSystem, UserTypesForCourse, Criteria
from data.fixtures import CoursesFactory, UsersFactory, CoursesAndUsersFactory, PostsFactory, PostsForQuestionsFactory, \
	PostsForAnswersFactory, CriteriaFactory, CriteriaAndCoursesFactory


class BasicTestData():
	def __init__(self):
		self.default_criteria = Criteria.query.first()
		self.main_course = self.create_course()
		self.secondary_course = self.create_course()
		self.main_course_default_criteria = self.add_criteria_course(self.default_criteria, self.main_course)
		self.secondary_course_default_criteria = self.add_criteria_course(self.default_criteria, self.secondary_course)
		self.authorized_instructor = self.create_instructor()
		self.authorized_ta = self.create_normal_user()
		self.authorized_student = self.create_normal_user()
		self.unauthorized_instructor = self.create_instructor() # unauthorized to the main course
		self.unauthorized_student = self.create_normal_user()
		self.enrol_instructor(self.authorized_instructor, self.main_course)
		self.enrol_ta(self.authorized_ta, self.main_course)
		self.enrol_student(self.authorized_student, self.main_course)
		self.enrol_instructor(self.unauthorized_instructor, self.secondary_course)
		self.enrol_student(self.unauthorized_student, self.secondary_course)
	def create_course(self):
		course = CoursesFactory()
		db.session.commit()
		return course
	def add_criteria_course(self, criteria, course):
		course_criteria = CriteriaAndCoursesFactory(criteria_id=criteria.id, courses_id=course.id)
		db.session.commit()
		return course_criteria
	def create_instructor(self):
		return self.create_user(UserTypesForSystem.TYPE_INSTRUCTOR)
	def create_normal_user(self):
		return self.create_user(UserTypesForSystem.TYPE_NORMAL)
	def create_user(self, type):
		sys_type = UserTypesForSystem.query.filter_by(name=type).first()
		user = UsersFactory(usertypesforsystem_id=sys_type.id)
		db.session.commit()
		return user
	def enrol_student(self, user, course):
		self.enrol_user(user, course, UserTypesForCourse.TYPE_STUDENT)
	def enrol_instructor(self, user, course):
		self.enrol_user(user, course, UserTypesForCourse.TYPE_INSTRUCTOR)
	def enrol_ta(self, user, course):
		self.enrol_user(user, course, UserTypesForCourse.TYPE_TA)
	def enrol_user(self, user, course, type):
		course_type = UserTypesForCourse.query.filter_by(name=type).first()
		CoursesAndUsersFactory(courses_id=course.id, users_id=user.id,
							   usertypesforcourse_id=course_type.id)
		db.session.commit()
	def get_authorized_instructor(self):
		return self.authorized_instructor
	def get_authorized_ta(self):
		return self.authorized_ta
	def get_authorized_student(self):
		return self.authorized_student
	def get_course(self):
		return self.main_course
	def get_unauthorized_instructor(self):
		return self.unauthorized_instructor
	def get_unauthorized_student(self):
		return self.unauthorized_student
	def get_default_criteria(self):
		return self.default_criteria

class SimpleQuestionsTestData(BasicTestData):
	def __init__(self):
		BasicTestData.__init__(self)
		self.questions = []
		self.questions.append(self.create_question_in_answer_period(self.get_course(),\
			self.get_authorized_instructor()))
		self.questions.append(self.create_question_in_answer_period(self.get_course(), \
			self.get_authorized_instructor()))

	def create_question_in_judgement_period(self, course, author):
		answer_start = datetime.datetime.now() - datetime.timedelta(days=2)
		answer_end = datetime.datetime.now() - datetime.timedelta(days=1)
		return self.create_question(course, author, answer_start, answer_end)

	def create_question_in_answer_period(self, course, author):
		answer_start = datetime.datetime.now() - datetime.timedelta(days=1)
		answer_end = datetime.datetime.now() + datetime.timedelta(days=1)
		return self.create_question(course, author, answer_start, answer_end)

	def create_question(self, course, author, answer_start, answer_end):
		post = PostsFactory(courses_id = course.id, users_id = author.id)
		db.session.commit()
		question = PostsForQuestionsFactory(posts_id = post.id, answer_start = answer_start, answer_end = answer_end)
		db.session.commit()
		return question

	def get_questions(self):
		return self.questions

class SimpleAnswersTestData(SimpleQuestionsTestData):
	def __init__(self):
		SimpleQuestionsTestData.__init__(self)
		self.extra_student1 = self.create_normal_user()
		self.extra_student2 = self.create_normal_user()
		self.enrol_student(self.extra_student1, self.get_course())
		self.enrol_student(self.extra_student2, self.get_course())
		self.answers = []
		for question in self.get_questions():
			self.answers.append(self.create_answer(question, self.extra_student1))
			self.answers.append(self.create_answer(question, self.extra_student2))

	def create_answer(self, question, author):
		post = PostsFactory(courses_id = question.post.courses_id, users_id = author.id)
		db.session.commit()
		answer = PostsForAnswersFactory(postsforquestions_id=question.id, posts_id = post.id)
		db.session.commit()
		return answer

	def get_answers(self):
		return self.answers

	def get_extra_student1(self):
		return self.extra_student1

class JudgmentsTestData(SimpleAnswersTestData):
	def __init__(self):
		SimpleAnswersTestData.__init__(self)
		self.secondary_authorized_student = self.create_normal_user()
		self.enrol_student(self.secondary_authorized_student , self.get_course())
		self.authorized_student_with_no_answers = self.create_normal_user()
		self.enrol_student(self.authorized_student_with_no_answers , self.get_course())
		self.student_answers = copy.copy(self.answers)
		for question in self.get_questions():
			# make sure we're allowed to judge existing questions
			self.set_question_to_judgement_period(question)
			answer = self.create_answer(question, self.secondary_authorized_student )
			self.answers.append(answer)
			self.student_answers.append(answer)
			self.answers.append(answer)
			answer = self.create_answer(question, self.get_authorized_student())
			self.answers.append(answer)
			self.student_answers.append(answer)
			# add a TA and Instructor answer
			answer = self.create_answer(question, self.get_authorized_ta())
			self.answers.append(answer)
			answer = self.create_answer(question, self.get_authorized_instructor())
			self.answers.append(answer)
		self.answer_period_question = self.create_question_in_answer_period(
			self.get_course(), self.get_authorized_ta())
		self.questions.append(self.answer_period_question)

	def get_student_answers(self):
		return self.student_answers

	def get_question_in_answer_period(self):
		return self.answer_period_question

	def get_secondary_authorized_student(self):
		return self.secondary_authorized_student

	def get_authorized_student_with_no_answers(self):
		'''
		This user is required to make sure that the same answers don't show up in a pair. MUST keep
		make sure that this user does not submit any answers.
		'''
		return self.authorized_student_with_no_answers

	def set_question_to_judgement_period(self, question):
		question.answer_start = datetime.datetime.now() - datetime.timedelta(days=2)
		question.answer_end = datetime.datetime.now() - datetime.timedelta(days=1)
		db.session.add(question)
		db.session.commit()
		return question

class CriteriaTestData(BasicTestData):
	def __init__(self):
		BasicTestData.__init__(self)
		self.criteria = self.create_criteria(self.get_authorized_instructor())
		self.secondary_criteria = self.create_criteria(self.get_unauthorized_instructor())
		self.inactive_criteria_course = self.add_inactive_criteria_course(self.criteria, self.get_course())

	def create_criteria(self, user):
		name = factory.fuzzy.FuzzyText(length=4)
		description = factory.fuzzy.FuzzyText(length=8)
		criteria = CriteriaFactory(name=name, description=description, user=user)
		db.session.commit()
		return criteria

	def add_inactive_criteria_course(self, criteria, course):
		criteria_course = CriteriaAndCoursesFactory(courses_id=course.id, criteria_id=criteria.id, active=False)
		db.session.add(criteria_course)
		db.session.commit()
		return criteria_course

	def get_criteria(self):
		return self.criteria

	def get_secondary_criteria(self):
		return self.secondary_criteria

	def get_inactive_criteria_course(self):
		return self.inactive_criteria_course

