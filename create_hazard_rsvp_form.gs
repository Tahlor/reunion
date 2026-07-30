/**
 * Creates or updates the Hazard Family Reunion meal-planning Google Form.
 *
 * Each household supplies one rough estimate of adult-sized portions (0–12)
 * and marks which group meals it expects to attend. The estimate is for
 * planning only; it is not a reservation or a guarantee of food.
 *
 * Run createHazardMealRsvp() once for a new form. For the existing form from
 * the reunion site, run updateHazardMealRsvp() once instead.
 */

const EXISTING_FORM_ID = '1EeX2uRSJ2j9hLviIvzmF2GGObHn8Zrkfes_2t2P1XwQ';
const EXISTING_SPREADSHEET_ID = '19hImuDxS-7aYMUJw8jqrmwzovslg2vWw21evmaBE2Lg';
const FORM_TITLE = 'Hazard Family Reunion — Group Meal RSVP';
const MEALS = [
  'Sunday, Aug. 2 — 3:00 PM Provo Canyon - Mexican - Tacos, Nachos, Burritos',
  'Monday, Aug. 3 — dinner at Great Horned Owl Campground - BBQ Pork Sandwiches',
  'Tuesday, Aug. 4 — lunch at North Park by the Provo Recreation Center -- Chicken croissant sandwiches with fruit/cowboy caviar/ chips',
  'Wednesday, Aug. 5 — dinner at Great Horned Owl Campground (or possibly the pickleball court)',
  'Thursday, Aug. 6 — dinner and dance at the Montana Avenue backyard',
  'Friday, Aug. 7 — dinner at Great Horned Owl Campground'
];

function createHazardMealRsvp() {
  const form = FormApp.create(FORM_TITLE, true);
  const spreadsheet = SpreadsheetApp.create(FORM_TITLE + ' — Responses');
  form.setDestination(FormApp.DestinationType.SPREADSHEET, spreadsheet.getId());
  configureForm(form);
  SpreadsheetApp.flush();
  const responseSheet = waitForResponseSheet(spreadsheet);
  configureTotals(spreadsheet, responseSheet, form);
  return logResult(form, spreadsheet);
}

function updateHazardMealRsvp() {
  const form = FormApp.openById(EXISTING_FORM_ID);
  const spreadsheet = SpreadsheetApp.openById(EXISTING_SPREADSHEET_ID);
  configureForm(form);
  SpreadsheetApp.flush();
  const responseSheet = findResponseSheet(spreadsheet);
  if (!responseSheet) {
    throw new Error('Could not find the linked response sheet in the existing spreadsheet.');
  }
  configureTotals(spreadsheet, responseSheet, form);
  return logResult(form, spreadsheet);
}

function configureForm(form) {
  form
    .setTitle(FORM_TITLE)
    .setDescription(
      'Please submit one response per household. Give one rough estimate of your household\'s ' +
      'total adult-sized portions, then mark which group meals you expect to attend. This is ' +
      'for planning and shopping only; it is not a reservation, promise, or guarantee that food ' +
      'will be available. The form allows 0–12 portions per household, roughly 2 adults plus ' +
      '10 children. You can edit your response later if plans change.'
    )
    .setConfirmationMessage(
      'Thanks! Your planning estimate was recorded. This is not a reservation or a guarantee ' +
      'that food will be available. Save the “Edit your response” link in case plans change.'
    )
    .setAllowResponseEdits(true)
    .setCollectEmail(false)
    .setLimitOneResponsePerUser(false)
    .setProgressBar(true)
    .setPublishingSummary(false)
    .setShowLinkToRespondAgain(false)
    .setShuffleQuestions(false);

  while (form.getItems().length) {
    form.deleteItem(0);
  }

  form.addTextItem()
    .setTitle('Family / household name')
    .setRequired(true);

  form.addTextItem()
    .setTitle('Contact phone or email')
    .setHelpText('Optional; useful if the organizer has a meal question.')
    .setRequired(false);

  form.addListItem()
    .setTitle('Estimated adult-sized portions for your household')
    .setHelpText(
      'Planning estimate only, not a food guarantee. Count portions however seems reasonable ' +
      'for the people you know will attend. Maximum 12 per household.'
    )
    .setChoiceValues(Array.from({length: 13}, (_, index) => String(index)))
    .setRequired(true);

  MEALS.forEach((meal) => {
    form.addMultipleChoiceItem()
      .setTitle('Will your household attend: ' + meal + '?')
      .setChoiceValues(['Attending', 'Not attending'])
      .setRequired(true);
  });

  form.addParagraphTextItem()
    .setTitle('Dietary restrictions, allergies, or meal notes')
    .setRequired(false);
}

function findResponseSheet(spreadsheet) {
  const totalsSheet = spreadsheet.getSheetByName('Meal Totals');
  return spreadsheet.getSheets().find((sheet) => !totalsSheet || sheet.getSheetId() !== totalsSheet.getSheetId()) || null;
}

function waitForResponseSheet(spreadsheet) {
  let responseSheet = null;
  for (let attempt = 0; attempt < 20 && !responseSheet; attempt += 1) {
    Utilities.sleep(500);
    responseSheet = findResponseSheet(spreadsheet);
  }
  if (!responseSheet) {
    throw new Error(
      'The form was created, but the response sheet was not ready. Open the spreadsheet and ' +
      'run configureTotals manually.'
    );
  }
  return responseSheet;
}

function configureTotals(spreadsheet, responseSheet, form) {
  let totalsSheet = spreadsheet.getSheetByName('Meal Totals');
  if (!totalsSheet) {
    totalsSheet = spreadsheet.insertSheet('Meal Totals', 0);
  }
  totalsSheet.clear();

  const responseTab = responseSheet.getName().replace(/'/g, "''");
  const responseRef = "'" + responseTab + "'!";
  const mealRows = [
    [MEALS[0], 'E'],
    [MEALS[1], 'F'],
    [MEALS[2], 'G'],
    [MEALS[3], 'H'],
    [MEALS[4], 'I'],
    [MEALS[5], 'J']
  ];

  totalsSheet.getRange('A1:C7').setValues([
    ['Group meal', 'Estimated adult-sized portions', 'Households attending'],
    ...mealRows.map(([name]) => [name, '', ''])
  ]);

  mealRows.forEach(([name, attendanceColumn], index) => {
    const row = index + 2;
    totalsSheet.getRange(row, 2).setFormula(
      '=SUM(ARRAYFORMULA(IF(' + responseRef + attendanceColumn + '2:' + attendanceColumn +
      '="Attending",IFERROR(VALUE(' + responseRef + 'D2:D),0),0)))'
    );
    totalsSheet.getRange(row, 3).setFormula(
      '=COUNTIF(' + responseRef + attendanceColumn + '2:' + attendanceColumn + ',"Attending")'
    );
  });

  totalsSheet.getRange('A9:B14').setValues([
    ['Organizer links', ''],
    ['Households responding', ''],
    ['Public RSVP form', form.getPublishedUrl()],
    ['Edit the form', form.getEditUrl()],
    ['Response spreadsheet', spreadsheet.getUrl()],
    ['Planning note', 'Portion totals are estimates, not food guarantees.']
  ]);
  totalsSheet.getRange('B10').setFormula('=COUNTA(' + responseRef + 'B2:B)');
  totalsSheet.getRange('A1:C1').setFontWeight('bold');
  totalsSheet.getRange('A9:B9').setFontWeight('bold');
  totalsSheet.setFrozenRows(1);
  totalsSheet.autoResizeColumns(1, 3);
  totalsSheet.setColumnWidth(1, 280);
  totalsSheet.setColumnWidth(2, 260);
  totalsSheet.setColumnWidth(3, 160);
}

function logResult(form, spreadsheet) {
  const result = [
    'RSVP form: ' + form.getPublishedUrl(),
    'Edit form: ' + form.getEditUrl(),
    'Responses and totals: ' + spreadsheet.getUrl(),
    '',
    'The form now collects one estimate-only adult-sized portion total (0–12) and one attendance choice per meal.'
  ].join('\n');
  console.log(result);
  Logger.log(result);
  return result;
}
