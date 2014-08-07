## Template for creating a new table. Note, the first 3 are taken care of by
## the default_table_args defined in database.py.
## * If MySQL, table engine must be InnoDB, for native foreign key support.
## * The default character set must be utf8, cause utf8 everywhere makes
##	 text encodings much easier to deal with.
## * Collation is using the slightly slower utf8_unicode_ci due to it's better
##	 conformance to human expectations for sorting. 
## * There must always be a primary key id field. 
## * creation_time and modification_time fields are self updating, they're nice
##	 to have for troubleshooting, but not all tables need them.
## * Additional fields given are meant for reference only. 
## * Foreign keys must be named in the format of <tablename>_id for
##	 consistency. 
## * 'ON DELETE CASCADE' is the preferred resolution method so that we don't
##	 have to worry about database consistency as much.
## * Junction tables names must be the two table's names, connected by
##	 "And".
## * Some tables might have subcategories, use the word "For" to indicated the
##	 subcategory, e.g.: we have a "Posts" table for all posts and a 
##	 "PostsForQuestions" table for posts that are meant to be questions

import hashlib
from sqlalchemy import event

from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import reconstructor, synonym, validates
from sqlalchemy.sql import func

#  import the context under an app-specific name (so it can easily be replaced later)
from passlib.apps import custom_app_context as pwd_context

from flask.ext.login import UserMixin

#################################################
# Users
#################################################

# User types at the course level
from .core import db

# All tables should have this set of options enabled to make porting easier.
# In case we have to move to MariaDB instead of MySQL, e.g.: InnoDB in MySQL
# is replaced by XtraDB.
default_table_args = {'mysql_charset': 'utf8', 'mysql_engine': 'InnoDB',
					  'mysql_collate': 'utf8_unicode_ci'}


class UserTypesForCourse(db.Model):
	__tablename__ = "UserTypesForCourse"
	__table_args__ = default_table_args

	id = db.Column(db.Integer, primary_key=True, nullable=False)
	name = db.Column(db.String(255), unique=True, nullable=False)

	# constants for the user types
	TYPE_DROPPED = "Dropped"
	TYPE_STUDENT = "Student"
	TYPE_TA = "Teaching Assistant"
	TYPE_INSTRUCTOR = "Instructor"

# User types at the system level
class UserTypesForSystem(db.Model):
	__tablename__ = "UserTypesForSystem"
	__table_args__ = default_table_args

	id = db.Column(db.Integer, primary_key=True, nullable=False)
	name = db.Column(db.String(255), unique=True, nullable=False)

	TYPE_NORMAL = "Normal User"
	TYPE_INSTRUCTOR = "Instructor"
	TYPE_SYSADMIN = "System Administrator"

def hash_password(password, is_admin=False):
	category = None
	if is_admin:
		# enables more rounds for admin passwords
		category = "admin"
	return pwd_context.encrypt(password, category=category)

# Flask-Login requires the user class to have some methods, the easiest way
# to get those methods is to inherit from the UserMixin class.
class Users(db.Model, UserMixin):
	__tablename__ = 'Users'
	__table_args__ = default_table_args

	id = db.Column(db.Integer, primary_key=True, nullable=False)
	username = db.Column(db.String(255), unique=True, nullable=False)
	_password = db.Column(db.String(255), unique=False, nullable=False)

	# Apparently, enabling the equivalent of ON DELETE CASCADE requires
	# the ondelete option in the foreign key and the cascade + passive_deletes
	# option in db.relationship().
	usertypesforsystem_id = db.Column(
		db.Integer,
		db.ForeignKey('UserTypesForSystem.id', ondelete="CASCADE"),
		nullable=False)
	usertypeforsystem = db.relationship("UserTypesForSystem")

	email = db.Column(db.String(254))  # email addresses are max 254 characters, no
	# idea if the unicode encoding of email addr
	# changes this.
	firstname = db.Column(db.String(255))
	lastname = db.Column(db.String(255))
	displayname = db.Column(db.String(255), unique=True, nullable=True)
	lastonline = db.Column(db.DateTime)
	# Note that MySQL before 5.6.5 doesn't allow more than one auto init/update
	# column for timestamps! Auto init/update after 5.6.5 allows multiple 
	# columns and can be applied to the db.DateTime field as well. This means that
	# 'modified' can be counted on to be auto init/updated for manual
	# (non-SQLAlchemy) database operations while 'created' will not.
	modified = db.Column(
		db.TIMESTAMP,
		default=func.current_timestamp(),
		onupdate=func.current_timestamp(),
		nullable=False)
	created = db.Column(db.TIMESTAMP, default=func.current_timestamp(),
					 nullable=False)
	coursesandusers = db.relationship("CoursesAndUsers")

	def _get_password(self):
		return self._password

	def _set_password(self, password):
		self._password = hash_password(password)

	password = property(_get_password, _set_password)
	password = synonym('_password', descriptor=password)

	@hybrid_property
	def fullname(self):
		if self.firstname and self.lastname:
			return '%s %s' % (self.firstname, self.lastname)
		elif self.firstname:  # only first name provided
			return self.firstname
		elif self.lastname:  # only last name provided
			return self.lastname
		else:
			return None

	# According to gravatar's hash specs
	# 	1.Trim leading and trailing whitespace from an email address
	# 	2.Force all characters to lower-case
	# 	3.md5 hash the final string
	# Defaults to a hash of the user's username if no email is available
	@hybrid_property
	def avatar(self):
		hash_input = self.username
		if self.email:
			hash_input = self.email
		m = hashlib.md5()
		m.update(hash_input.strip().lower().encode('utf-8'))
		return m.hexdigest()

	def verify_password(self, password):
		return pwd_context.verify(password, self.password)

	def update_lastonline(self):
		self.lastonline = func.current_timestamp()
		db.session.add(self)
		db.session.commit()


# # create a default root user with sysadmin role
# @event.listens_for(Users.__table__, "after_create", propagate=True)
# def populate_users(target, connection, **kw):
# 	sysadmintype = UserTypesForSystem.query.filter(
# 		UserTypesForSystem.name == UserTypesForSystem.TYPE_SYSADMIN).first()
# 	user = Users(username="root", displayname="root")
# 	user.set_password("password", True)
# 	user.usertypeforsystem = sysadmintype
# 	db_session.add(user)
# 	db_session.commit()


#################################################
# Courses and Enrolment
#################################################

class Courses(db.Model):
	__tablename__ = 'Courses'
	__table_args__ = default_table_args

	id = db.Column(db.Integer, primary_key=True, nullable=False)
	name = db.Column(db.String(255), unique=True, nullable=False)
	description = db.Column(db.Text)
	available = db.Column(db.Boolean, default=True, nullable=False)
	coursesandusers = db.relationship("CoursesAndUsers")
	_criteriaandcourses = db.relationship("CriteriaAndCourses")
	# allow students to make question posts
	enable_student_create_questions = db.Column(db.Boolean, default=False, nullable=False)
	enable_student_create_tags = db.Column(db.Boolean, default=False, nullable=False)
	modified = db.Column(
		db.TIMESTAMP,
		default=func.current_timestamp(),
		onupdate=func.current_timestamp(),
		nullable=False)
	created = db.Column(db.TIMESTAMP, default=func.current_timestamp(),
					 nullable=False)
	@hybrid_property
	def criteriaandcourses(self):
		'''
		Adds the default criteria to newly created courses which doesn't have any criteria yet.
		This is a complete hack. I'd implement this using sqlalchemy's event system instead but
		it seems that events doesn't work right during test cases for some reason.
		'''
		if not self._criteriaandcourses:
			default_criteria = Criteria.query.first()
			criteria_and_course = CriteriaAndCourses(criterion=default_criteria, courses_id=self.id)
			db.session.add(criteria_and_course)
			db.session.commit()
		return self._criteriaandcourses

# A "junction table" in sqlalchemy is called a many-to-many pattern. Such a
# table can be automatically created by sqlalchemy from db.relationship
# definitions along. But if additional fields are needed, then we can
# explicitly define such a table using the "association object" pattern.
# For determining a course's users, we're using the association object approach
# since we need to declare the user's role in the course.
class CoursesAndUsers(db.Model):
	__tablename__ = 'CoursesAndUsers'

	id = db.Column(db.Integer, primary_key=True, nullable=False)
	courses_id = db.Column(db.Integer, db.ForeignKey("Courses.id"), nullable=False)
	course = db.relationship("Courses")
	users_id = db.Column(db.Integer, db.ForeignKey("Users.id"), nullable=False)
	user = db.relationship("Users")
	usertypesforcourse_id = db.Column(
		db.Integer,
		db.ForeignKey('UserTypesForCourse.id', ondelete="CASCADE"),
		nullable=False)
	usertypeforcourse = db.relationship("UserTypesForCourse")
	modified = db.Column(
		db.TIMESTAMP,
		default=func.current_timestamp(),
		onupdate=func.current_timestamp(),
		nullable=False)
	created = db.Column(db.TIMESTAMP, default=func.current_timestamp(),
					 nullable=False)
	__table_args__ = (
		# prevent duplicate user in courses
		db.UniqueConstraint('courses_id', 'users_id', name='_unique_user_and_course'),
		default_table_args
	)


#################################################
# Tags for Posts, each course has their own set of tags
#################################################

class Tags(db.Model):
	__tablename__ = 'Tags'
	__table_args__ = default_table_args

	id = db.Column(db.Integer, primary_key=True, nullable=False)
	name = db.Column(db.String(255), unique=True, nullable=False)
	courses_id = db.Column(
		db.Integer,
		db.ForeignKey('Courses.id', ondelete="CASCADE"),
		nullable=False)
	course = db.relationship("Courses")
	created = db.Column(db.TIMESTAMP, default=func.current_timestamp(),
					 nullable=False)


#################################################
# Posts - content postings made by users
#################################################

class Posts(db.Model):
	__tablename__ = 'Posts'
	__table_args__ = default_table_args

	id = db.Column(db.Integer, primary_key=True, nullable=False)
	users_id = db.Column(
		db.Integer,
		db.ForeignKey('Users.id', ondelete="CASCADE"),
		nullable=False)
	user = db.relationship("Users")
	courses_id = db.Column(
		db.Integer,
		db.ForeignKey('Courses.id', ondelete="CASCADE"),
		nullable=False)
	course = db.relationship("Courses")
	content = db.Column(db.Text)
	modified = db.Column(
		db.TIMESTAMP,
		default=func.current_timestamp(),
		onupdate=func.current_timestamp(),
		nullable=False)
	created = db.Column(db.TIMESTAMP, default=func.current_timestamp(),
					 nullable=False)

class PostsForQuestions(db.Model):
	__tablename__ = 'PostsForQuestions'
	__table_args__ = default_table_args

	id = db.Column(db.Integer, primary_key=True, nullable=False)
	posts_id = db.Column(
		db.Integer,
		db.ForeignKey('Posts.id', ondelete="CASCADE"),
		nullable=False)
	post = db.relationship("Posts")
	title = db.Column(db.String(255))
	answers = db.relationship("PostsForAnswers")
	comments = db.relationship("PostsForQuestionsAndPostsForComments")
	modified = db.Column(
		db.TIMESTAMP,
		default=func.current_timestamp(),
		onupdate=func.current_timestamp(),
		nullable=False)

	@hybrid_property
	def courses_id(self):
		return self.post.courses_id
	@hybrid_property
	def answers_count(self):
		return len(self.answers)
	@hybrid_property
	def comments_count(self):
		return len(self.comments)
	@hybrid_property
	def total_comments_count(self):
		counts = [a.comments_count for a in self.answers]
		return (sum(counts) + self.comments_count)

class PostsForAnswers(db.Model):
	__tablename__ = 'PostsForAnswers'
	__table_args__ = default_table_args

	id = db.Column(db.Integer, primary_key=True, nullable=False)
	posts_id = db.Column(
		db.Integer,
		db.ForeignKey('Posts.id', ondelete="CASCADE"),
		nullable=False)
	post = db.relationship("Posts")
	postsforquestions_id = db.Column(
		db.Integer,
		db.ForeignKey('PostsForQuestions.id', ondelete="CASCADE"),
		nullable=False)
	question = db.relationship("PostsForQuestions")
	comments = db.relationship("PostsForAnswersAndPostsForComments")

	@hybrid_property
	def courses_id(self):
		return self.post.courses_id
	@hybrid_property
	def users_id(self):
		return self.post.user.id
	@hybrid_property
	def comments_count(self):
		return len(self.comments)

class PostsForComments(db.Model):
	__tablename__ = 'PostsForComments'
	__table_args__ = default_table_args

	id = db.Column(db.Integer, primary_key=True, nullable=False)
	posts_id = db.Column(
		db.Integer,
		db.ForeignKey('Posts.id', ondelete="CASCADE"),
		nullable=False)
	post = db.relationship("Posts")

class PostsForQuestionsAndPostsForComments(db.Model):
	__tablename__ = 'PostsForQuestionsAndPostsForComments'
	__table_args__ = default_table_args

	id = db.Column(db.Integer, primary_key=True, nullable=False)
	postsforquestions_id = db.Column(
		db.Integer,
		db.ForeignKey('PostsForQuestions.id', ondelete="CASCADE"),
		nullable=False)
	postsforquestions = db.relationship("PostsForQuestions")
	postsforcomments_id = db.Column(
		db.Integer,
		db.ForeignKey('PostsForComments.id', ondelete="CASCADE"),
		nullable=False)
	postsforcomments = db.relationship("PostsForComments")

	@hybrid_property
	def courses_id(self):
		return self.postsforcomments.post.courses_id
	@hybrid_property
	def users_id(self):
		return self.postsforcomments.post.user.id
	@hybrid_property
	def content(self):
		return self.postsforcomments.post.content

class PostsForAnswersAndPostsForComments(db.Model):
	__tablename__ = 'PostsForAnswersAndPostsForComments'
	__table_args__ = default_table_args

	id = db.Column(db.Integer, primary_key=True, nullable=False)
	postsforanswers_id = db.Column(
		db.Integer,
		db.ForeignKey('PostsForAnswers.id', ondelete="CASCADE"),
		nullable=False)
	postsforanswers = db.relationship("PostsForAnswers")
	postsforcomments_id = db.Column(
		db.Integer,
		db.ForeignKey('PostsForComments.id', ondelete="CASCADE"),
		nullable=False)
	postsforcomments = db.relationship("PostsForComments")

	@hybrid_property
	def courses_id(self):
		return self.postsforcomments.post.courses_id
	@hybrid_property
	def users_id(self):
		return self.postsforcomments.post.user.id
	@hybrid_property
	def content(self):
		return self.postsforcomments.post.content
	

#################################################
# Criteria - What users should judge answers by
#################################################

class Criteria(db.Model):
	__tablename__ = 'Criteria'
	__table_args__ = default_table_args

	id = db.Column(db.Integer, primary_key=True, nullable=False)
	name = db.Column(db.String(255), unique=True, nullable=False)
	description = db.Column(db.Text)
	# user who made this criteria
	users_id = db.Column(
		db.Integer,
		db.ForeignKey('Users.id', ondelete="CASCADE"),
		nullable=False)
	user = db.relationship("Users")
	modified = db.Column(
		db.TIMESTAMP,
		default=func.current_timestamp(),
		onupdate=func.current_timestamp(),
		nullable=False)
	created = db.Column(db.TIMESTAMP, default=func.current_timestamp(),
					 nullable=False)


# each course can have different criterias
class CriteriaAndCourses(db.Model):
	__tablename__ = 'CriteriaAndCourses'
	__table_args__ = default_table_args

	id = db.Column(db.Integer, primary_key=True, nullable=False)
	criteria_id = db.Column(
		db.Integer,
		db.ForeignKey('Criteria.id', ondelete="CASCADE"),
		nullable=False)
	criterion = db.relationship("Criteria")
	courses_id = db.Column(
		db.Integer,
		db.ForeignKey('Courses.id', ondelete="CASCADE"),
		nullable=False)
	course = db.relationship("Courses")


#################################################
# Scores - The calculated score of the answer
#################################################

class Scores(db.Model):
	__tablename__ = 'Scores'
	__table_args__ = default_table_args

	id = db.Column(db.Integer, primary_key=True, nullable=False)
	name = db.Column(db.String(255), unique=True, nullable=False)
	criteria_id = db.Column(
		db.Integer,
		db.ForeignKey('Criteria.id', ondelete="CASCADE"),
		nullable=False)
	criteria = db.relationship("Criteria")
	postsforanswers_id = db.Column(
		db.Integer,
		db.ForeignKey('PostsForAnswers.id', ondelete="CASCADE"),
		nullable=False)
	answer = db.relationship("PostsForAnswers")
	# number of times this answer has been judged
	rounds = db.Column(db.Integer, default=0)
	# number of times this answer has been picked as the better one
	wins = db.Column(db.Integer, default=0)
	# calculated score based on all previous judgements
	score = db.Column(db.Float, default=0)


#################################################
# Judgements - User's judgements on the answers
#################################################

class AnswerPairings(db.Model):
	__tablename__ = 'AnswerPairings'
	__table_args__ = default_table_args

	id = db.Column(db.Integer, primary_key=True)
	postsforquestions_id = db.Column(
		db.Integer,
		db.ForeignKey('PostsForQuestions.id', ondelete="CASCADE"),
		nullable=False)
	question = db.relationship("PostsForQuestions")
	postsforanswers_id1 = db.Column(
		db.Integer,
		db.ForeignKey('PostsForAnswers.id', ondelete="CASCADE"),
		nullable=False)
	answer1 = db.relationship("PostsForAnswers", foreign_keys=[postsforanswers_id1])
	postsforanswers_id2 = db.Column(
		db.Integer,
		db.ForeignKey('PostsForAnswers.id', ondelete="CASCADE"),
		nullable=False)
	answer2 = db.relationship("PostsForAnswers", foreign_keys=[postsforanswers_id2])
	modified = db.Column(
		db.TIMESTAMP,
		default=func.current_timestamp(),
		onupdate=func.current_timestamp(),
		nullable=False)
	created = db.Column(db.TIMESTAMP, default=func.current_timestamp(),
					 nullable=False)


class Judgements(db.Model):
	__tablename__ = 'Judgements'
	__table_args__ = default_table_args

	id = db.Column(db.Integer, primary_key=True)
	users_id = db.Column(
		db.Integer,
		db.ForeignKey('Users.id', ondelete="CASCADE"),
		nullable=False)
	user = db.relationship("Users")
	answerpairings_id = db.Column(
		db.Integer,
		db.ForeignKey('AnswerPairings.id', ondelete="CASCADE"),
		nullable=False)
	answerpairing = db.relationship("AnswerPairings")
	criteriaandcourses_id = db.Column(
		db.Integer,
		db.ForeignKey('CriteriaAndCourses.id', ondelete="CASCADE"),
		nullable=False)
	course_criterion = db.relationship("CriteriaAndCourses")
	postsforanswers_id_winner = db.Column(
		db.Integer,
		db.ForeignKey('PostsForAnswers.id', ondelete="CASCADE"),
		nullable=False)
	answer_winner = db.relationship("PostsForAnswers")
	modified = db.Column(
		db.TIMESTAMP,
		default=func.current_timestamp(),
		onupdate=func.current_timestamp(),
		nullable=False)
	created = db.Column(db.TIMESTAMP, default=func.current_timestamp(),
					 nullable=False)

	@hybrid_property
	def courses_id(self):
		return self.course_criterion.courses_id

class LTIInfo(db.Model):
	__tablename__ = 'LTIInfo'
	__table_args__ = default_table_args

	id = db.Column(db.Integer, primary_key=True)
	LTIid = db.Column(db.String(100))
	LTIURL = db.Column(db.String(100))
	courses_id = db.Column(
		db.Integer,
		db.ForeignKey('Courses.id', ondelete="CASCADE"),
		nullable=False)
	course = db.relationship("Courses")

