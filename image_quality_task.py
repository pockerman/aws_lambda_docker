def handler(event, context):
    db_session = get_db_session()
    try:
        task_id = event['task_id']
        task_data = await ReadImageCalculationTaskCURDAPI.find_one(criteria={'_id': bson.ObjectId(task_id)},
                                                                   db_session=db_session)

        if task_data is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail=f"Task with id={task_id} nod found")

        task_errors = ""
        survey_id = task_data['survey_idx']
        survey_item_id = task_data['survey_item_idx']
        checkpoint_id = task_data['checkpoint_idx']

        # get the images one by one
        images = ReadImageCURDAPI.find(criteria={'survey_idx': bson.ObjectId(survey_id),
                                                 'survey_item_idx': bson.ObjectId(survey_item_id),
                                                 'checkpoint_idx': bson.ObjectId(checkpoint_id)},
                                       projection={'aws_idx': 1, 'filename': 1}, db_session=db_session)

        images = [img async for img in images]

        print(f"Number of images= {len(images)}")

        s3_bucket_credentials = AWSBucketCredentials(aws_access_key=AWS_ACCESS_KEY,
                                                     aws_region_name=AWS_REGION_NAME,
                                                     aws_bucket_name=AWS_S3_BUCKET,
                                                     aws_secret_access_key=AWS_SECRET_ACCESS_KEY)

        images_prefix = images[0]['aws_idx']

        if not images_prefix.endswith("/"):
            images_prefix += "/"

        # get all the images
        img_batch = ImagePathBatch(aws_bucket_credentials=s3_bucket_credentials,
                                   images_prefix=images_prefix)

        for img in img_batch:
            print(f"Img['img']={img['img']}")
            key = img['img']
            file_byte_string = img_batch.s3_client.get_object(Bucket=s3_bucket_credentials.aws_bucket_name,
                                                              Key=key)
            try:
                quality = brisque_quality_from_obj(file_byte_string['Body'].read())

                # get the images one by one
                images = await UpdateImageCRUDAPI.update_one(criteria={'survey_idx': bson.ObjectId(survey_id),
                                                                       'survey_item_idx': bson.ObjectId(survey_item_id),
                                                                       'checkpoint_idx': bson.ObjectId(checkpoint_id)},
                                                             update_data={'image_quality': quality,
                                                                          'image_quality_algo': IMAGE_QUALITY_ALGO},
                                                             db_session=db_session)


            except Exception as e:
                # calculation failed
                failed_image = f"Image= {key} calculation failed. Exception message "
                task_errors += failed_image
                task_errors += str(e)
                task_errors += "\n"
                pass

    if task_errors == "":
        task_errors = "NONE"

    await UpdateImageCalculationTaskCRUDAPI.update_one(criteria={'_id': bson.ObjectId(task_id)},
                                                       update_data={'task_status': 'FINISHED',
                                                                    'errors': task_errors},
                                                       db_session=db_session)

    return JSONResponse(status_code=status.HTTP_200_OK, content="Task finished")