MERGE dbo.ElderlyUsers AS target
USING (VALUES
    (N'user-1', N'김영희', 1948, N'관절 가동 범위 유지'),
    (N'user-2', N'박철수', 1951, N'낙상 예방')
) AS source (user_id, name, birth_year, memo)
ON target.user_id = source.user_id
WHEN MATCHED THEN
    UPDATE SET
        name = source.name,
        birth_year = source.birth_year,
        memo = source.memo
WHEN NOT MATCHED THEN
    INSERT (user_id, name, birth_year, memo)
    VALUES (source.user_id, source.name, source.birth_year, source.memo);
GO

MERGE dbo.MirrorDevices AS target
USING (VALUES
    (N'mirror-demo-001', N'Rehab Mirror Demo', NULL, N'waiting', NULL)
) AS source (mirror_id, device_name, pairing_code, pairing_status, paired_user_id)
ON target.mirror_id = source.mirror_id
WHEN MATCHED THEN
    UPDATE SET
        device_name = source.device_name,
        updated_at = SYSUTCDATETIME()
WHEN NOT MATCHED THEN
    INSERT (mirror_id, device_name, pairing_code, pairing_status, paired_user_id)
    VALUES (
        source.mirror_id,
        source.device_name,
        source.pairing_code,
        source.pairing_status,
        source.paired_user_id
    );
GO

MERGE dbo.Exercises AS target
USING (VALUES
    (
        N'shoulder',
        N'앉아서 양팔 들고 몸통 돌리기',
        N'어깨·몸통 예방 운동',
        N'의자에 앉아 양팔을 들고 몸통을 좌우로 천천히 움직입니다.',
        N'/static/videos/shoulder.mp4',
        CAST(1 AS BIT),
        N'분석 가능'
    ),
    (
        N'rom_shoulder',
        N'관절 가동 범위 점검',
        N'관절 가동 범위',
        N'카메라로 어깨 관절 움직임을 인식하여 가동 범위를 확인합니다.',
        N'/static/videos/rom_shoulder_demo.mp4',
        CAST(1 AS BIT),
        N'점검 가능'
    ),
    (
        N'knee',
        N'무릎 굽혔다 펴기',
        N'무릎 질환 예방',
        N'무릎을 안정적으로 굽혔다 펴며 하체 움직임을 확인합니다.',
        N'/static/videos/knee.mp4',
        CAST(0 AS BIT),
        N'준비 중'
    ),
    (
        N'flexibility',
        N'옆구리 늘리기',
        N'유연성',
        N'몸통을 천천히 기울여 옆구리와 허리를 이완합니다.',
        N'/static/videos/flexibility.mp4',
        CAST(0 AS BIT),
        N'준비 중'
    ),
    (
        N'balance',
        N'균형 잡기',
        N'낙상 예방',
        N'자세 흔들림을 줄이고 일상 보행 안정성을 높입니다.',
        N'/static/videos/balance.mp4',
        CAST(0 AS BIT),
        N'준비 중'
    )
) AS source (
    exercise_key,
    title,
    category,
    description,
    video_path,
    is_supported,
    status_label
)
ON target.exercise_key = source.exercise_key
WHEN MATCHED THEN
    UPDATE SET
        title = source.title,
        category = source.category,
        description = source.description,
        video_path = source.video_path,
        is_supported = source.is_supported,
        status_label = source.status_label
WHEN NOT MATCHED THEN
    INSERT (
        exercise_key,
        title,
        category,
        description,
        video_path,
        is_supported,
        status_label
    )
    VALUES (
        source.exercise_key,
        source.title,
        source.category,
        source.description,
        source.video_path,
        source.is_supported,
        source.status_label
    );
GO
