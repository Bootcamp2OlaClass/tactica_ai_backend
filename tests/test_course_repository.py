from datetime import date

from app.models.course import CourseStatus
from app.models.semester import Semester, SemesterStatus
from app.models.user import User, UserRole
from app.repositories.course_repository import (
    count_courses,
    create_course,
    find_duplicate_course_code,
    get_course_by_id,
    list_courses_by_semester,
    list_courses_by_user,
    soft_delete_course,
    update_course,
)


from datetime import date

from app.models.semester import Semester, SemesterStatus
from app.models.user import User, UserRole
from app.repositories.course_repository import create_course


def test_create_course(db_session):
    user = User(
        email="test@example.com",
        password_hash="hashed-password",
        full_name="Test User",
        role=UserRole.STUDENT,
    )

    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    semester = Semester(
        user_id=user.id,
        name="Fall 2026",
        academic_year=2026,
        start_date=date(2026, 8, 24),
        end_date=date(2026, 12, 15),
        status=SemesterStatus.ACTIVE,
        is_deleted=False,
    )

    db_session.add(semester)
    db_session.commit()
    db_session.refresh(semester)

    course_data = {
        "semester_id": semester.id,
        "course_code": "COSC-1437",
        "name": "Programming Fundamentals II",
        "credits": 4,
        "status": "ACTIVE",
        "is_deleted": False,
    }

    course = create_course(
        db=db_session,
        course_data=course_data,
    )

    assert course.id is not None
    assert course.semester_id == semester.id
    assert course.course_code == "COSC-1437"
    assert course.name == "Programming Fundamentals II"


def test_get_course_by_id(db_session):
    user = User(
        email="owner@example.com",
        password_hash="hashed-password",
        full_name="Course Owner",
        role=UserRole.STUDENT,
    )

    other_user = User(
        email="other@example.com",
        password_hash="hashed-password",
        full_name="Other User",
        role=UserRole.STUDENT,
    )

    db_session.add_all([user, other_user])
    db_session.commit()
    db_session.refresh(user)
    db_session.refresh(other_user)

    semester = Semester(
        user_id=user.id,
        name="Fall 2026",
        academic_year=2026,
        start_date=date(2026, 8, 24),
        end_date=date(2026, 12, 15),
        status=SemesterStatus.ACTIVE,
        is_deleted=False,
    )

    db_session.add(semester)
    db_session.commit()
    db_session.refresh(semester)

    course = create_course(
        db=db_session,
        course_data={
            "semester_id": semester.id,
            "course_code": "COSC-1437",
            "name": "Programming Fundamentals II",
            "credits": 4,
            "status": "ACTIVE",
            "is_deleted": False,
        },
    )

    owner_result = get_course_by_id(
        db=db_session,
        course_id=course.id,
        user_id=user.id,
    )

    other_user_result = get_course_by_id(
        db=db_session,
        course_id=course.id,
        user_id=other_user.id,
    )

    assert owner_result is not None
    assert owner_result.id == course.id
    assert other_user_result is None


def test_find_duplicate_course_code(db_session):
    user = User(
        email="duplicate@example.com",
        password_hash="hashed-password",
        full_name="Duplicate User",
        role=UserRole.STUDENT,
    )

    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    semester = Semester(
        user_id=user.id,
        name="Fall 2026",
        academic_year=2026,
        start_date=date(2026, 8, 24),
        end_date=date(2026, 12, 15),
        status=SemesterStatus.ACTIVE,
        is_deleted=False,
    )

    db_session.add(semester)
    db_session.commit()
    db_session.refresh(semester)

    course = create_course(
        db=db_session,
        course_data={
            "semester_id": semester.id,
            "course_code": "COSC-1437",
            "name": "Programming Fundamentals II",
            "credits": 4,
            "status": CourseStatus.ACTIVE,
            "is_deleted": False,
        },
    )

    duplicate = find_duplicate_course_code(
        db=db_session,
        semester_id=semester.id,
        course_code="COSC-1437",
        user_id=user.id,
    )

    not_duplicate = find_duplicate_course_code(
        db=db_session,
        semester_id=semester.id,
        course_code="MATH-1314",
        user_id=user.id,
    )

    excluded = find_duplicate_course_code(
        db=db_session,
        semester_id=semester.id,
        course_code="COSC-1437",
        user_id=user.id,
        exclude_course_id=course.id,
    )

    assert duplicate is not None
    assert duplicate.id == course.id

    assert not_duplicate is None

    assert excluded is None


def test_list_courses_by_user(db_session):
    user = User(
        email="list@example.com",
        password_hash="hashed-password",
        full_name="List User",
        role=UserRole.STUDENT,
    )

    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    semester = Semester(
        user_id=user.id,
        name="Fall 2026",
        academic_year=2026,
        start_date=date(2026, 8, 24),
        end_date=date(2026, 12, 15),
        status=SemesterStatus.ACTIVE,
        is_deleted=False,
    )

    db_session.add(semester)
    db_session.commit()
    db_session.refresh(semester)

    create_course(
        db=db_session,
        course_data={
            "semester_id": semester.id,
            "course_code": "COSC-1437",
            "name": "Programming II",
            "credits": 4,
            "status": CourseStatus.ACTIVE,
            "is_deleted": False,
        },
    )

    create_course(
        db=db_session,
        course_data={
            "semester_id": semester.id,
            "course_code": "MATH-2413",
            "name": "Calculus I",
            "credits": 4,
            "status": CourseStatus.COMPLETED,
            "is_deleted": False,
        },
    )

    courses = list_courses_by_user(
        db=db_session,
        user_id=user.id,
    )

    assert len(courses) == 2

    search_result = list_courses_by_user(
        db=db_session,
        user_id=user.id,
        search="COSC",
    )

    assert len(search_result) == 1
    assert search_result[0].course_code == "COSC-1437"

    status_result = list_courses_by_user(
        db=db_session,
        user_id=user.id,
        status=CourseStatus.COMPLETED,
    )

    assert len(status_result) == 1
    assert status_result[0].course_code == "MATH-2413"


def test_list_courses_by_semester(db_session):
    user = User(
        email="semester@example.com",
        password_hash="hashed-password",
        full_name="Semester User",
        role=UserRole.STUDENT,
    )

    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    semester = Semester(
        user_id=user.id,
        name="Fall 2026",
        academic_year=2026,
        start_date=date(2026, 8, 24),
        end_date=date(2026, 12, 15),
        status=SemesterStatus.ACTIVE,
        is_deleted=False,
    )

    db_session.add(semester)
    db_session.commit()
    db_session.refresh(semester)

    create_course(
        db=db_session,
        course_data={
            "semester_id": semester.id,
            "course_code": "COSC-1437",
            "name": "Programming II",
            "credits": 4,
            "status": CourseStatus.ACTIVE,
            "is_deleted": False,
        },
    )

    create_course(
        db=db_session,
        course_data={
            "semester_id": semester.id,
            "course_code": "MATH-2413",
            "name": "Calculus I",
            "credits": 4,
            "status": CourseStatus.ACTIVE,
            "is_deleted": False,
        },
    )

    courses = list_courses_by_semester(
        db=db_session,
        semester_id=semester.id,
        user_id=user.id,
    )

    assert len(courses) == 2

    codes = {course.course_code for course in courses}

    assert "COSC-1437" in codes
    assert "MATH-2413" in codes


def test_count_courses(db_session):
    user = User(
        email="count@example.com",
        password_hash="hashed-password",
        full_name="Count User",
        role=UserRole.STUDENT,
    )

    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    semester = Semester(
        user_id=user.id,
        name="Fall 2026",
        academic_year=2026,
        start_date=date(2026, 8, 24),
        end_date=date(2026, 12, 15),
        status=SemesterStatus.ACTIVE,
        is_deleted=False,
    )

    db_session.add(semester)
    db_session.commit()
    db_session.refresh(semester)

    create_course(
        db=db_session,
        course_data={
            "semester_id": semester.id,
            "course_code": "COSC-1437",
            "name": "Programming II",
            "credits": 4,
            "status": CourseStatus.ACTIVE,
            "is_deleted": False,
        },
    )

    create_course(
        db=db_session,
        course_data={
            "semester_id": semester.id,
            "course_code": "MATH-2413",
            "name": "Calculus I",
            "credits": 4,
            "status": CourseStatus.COMPLETED,
            "is_deleted": False,
        },
    )

    total = count_courses(
        db=db_session,
        user_id=user.id,
    )

    assert total == 2

    active_count = count_courses(
        db=db_session,
        user_id=user.id,
        status=CourseStatus.ACTIVE,
    )

    assert active_count == 1

    search_count = count_courses(
        db=db_session,
        user_id=user.id,
        search="COSC",
    )

    assert search_count == 1


def test_update_course(db_session):
    user = User(
        email="update@example.com",
        password_hash="hashed-password",
        full_name="Update User",
        role=UserRole.STUDENT,
    )

    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    semester = Semester(
        user_id=user.id,
        name="Fall 2026",
        academic_year=2026,
        start_date=date(2026, 8, 24),
        end_date=date(2026, 12, 15),
        status=SemesterStatus.ACTIVE,
        is_deleted=False,
    )

    db_session.add(semester)
    db_session.commit()
    db_session.refresh(semester)

    course = create_course(
        db=db_session,
        course_data={
            "semester_id": semester.id,
            "course_code": "COSC-1437",
            "name": "Programming Fundamentals II",
            "credits": 4,
            "status": CourseStatus.ACTIVE,
            "is_deleted": False,
        },
    )

    updated_course = update_course(
        db=db_session,
        course=course,
        update_data={
            "name": "Advanced Programming",
            "credits": 3,
            "status": CourseStatus.COMPLETED,
        },
    )

    assert updated_course.id == course.id
    assert updated_course.name == "Advanced Programming"
    assert updated_course.credits == 3
    assert updated_course.status == CourseStatus.COMPLETED
    assert updated_course.course_code == "COSC-1437"


def test_soft_delete_course(db_session):
    user = User(
        email="delete@example.com",
        password_hash="hashed-password",
        full_name="Delete User",
        role=UserRole.STUDENT,
    )

    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    semester = Semester(
        user_id=user.id,
        name="Fall 2026",
        academic_year=2026,
        start_date=date(2026, 8, 24),
        end_date=date(2026, 12, 15),
        status=SemesterStatus.ACTIVE,
        is_deleted=False,
    )

    db_session.add(semester)
    db_session.commit()
    db_session.refresh(semester)

    course = create_course(
        db=db_session,
        course_data={
            "semester_id": semester.id,
            "course_code": "COSC-1437",
            "name": "Programming Fundamentals II",
            "credits": 4,
            "status": CourseStatus.ACTIVE,
            "is_deleted": False,
        },
    )

    deleted_course = soft_delete_course(
        db=db_session,
        course=course,
    )

    assert deleted_course.is_deleted is True
    assert deleted_course.deleted_at is not None

    result = get_course_by_id(
        db=db_session,
        course_id=course.id,
        user_id=user.id,
    )

    assert result is None